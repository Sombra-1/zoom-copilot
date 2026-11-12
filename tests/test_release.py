"""Startup, diagnostics, environment selection and shutdown regressions."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import setup
import zoom_copilot as app
from copilot_core import launcher
from copilot_core.diagnostics import record_failure


class LauncherTests(unittest.TestCase):
    def test_local_environment_is_selected_without_resolving_its_interpreter_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate = root / "venv" / ("Scripts/pythonw.exe" if os.name == "nt" else "bin/python")
            candidate.parent.mkdir(parents=True)
            candidate.touch()
            self.assertEqual(launcher.preferred_python(root, sys.executable), candidate.absolute())

    def test_relaunch_preserves_spaces_and_shell_characters_as_plain_arguments(self):
        with tempfile.TemporaryDirectory(prefix="copilot & test ") as folder:
            chosen = Path(folder) / "venv" / "pythonw.exe"
            with mock.patch.object(launcher, "preferred_python", return_value=chosen), \
                    mock.patch.object(launcher.subprocess, "Popen") as spawn:
                self.assertEqual(launcher.main(folder), 0)
            self.assertEqual(spawn.call_args.args[0][-1], str(Path(folder) / "launch.pyw"))
            self.assertEqual(spawn.call_args.kwargs["cwd"], folder)
            self.assertFalse(spawn.call_args.kwargs.get("shell", False))

    def test_startup_failure_is_visible_without_console(self):
        with mock.patch.object(launcher, "preferred_python", return_value=Path(sys.executable).absolute()), \
                mock.patch.object(launcher.runpy, "run_path", side_effect=ImportError("private content")), \
                mock.patch.object(launcher, "record_failure", return_value=Path("runtime.log")) as log, \
                mock.patch.object(launcher, "startup_error") as popup, \
                mock.patch.object(threading, "excepthook"):
            self.assertEqual(launcher.main(), 1)
        popup.assert_called_once_with(Path("runtime.log"))
        self.assertEqual(log.call_args.args[1], "startup")

    def test_diagnostics_omit_messages_and_source_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            try:
                raise ValueError("TOP_SECRET_TRANSCRIPT_AND_TOKEN")
            except ValueError:
                path = record_failure(sys.exc_info(), "test", directory=folder)
            content = path.read_text(encoding="utf-8")
            self.assertIn("ValueError", content)
            self.assertNotIn("TOP_SECRET", content)
            self.assertNotIn("raise ValueError", content)


class RuntimeReleaseTests(unittest.TestCase):
    def test_installer_rejects_pillow_versions_outside_validated_major(self):
        with mock.patch("importlib.metadata.version", return_value="12.3.0"):
            self.assertFalse(setup.check_package("PIL"))
        with mock.patch("importlib.metadata.version", return_value="13.0.0"):
            try:
                __import__("PIL")
            except ImportError:
                return
            self.assertTrue(setup.check_package("PIL"))

    def test_large_screen_images_resize_and_encode_with_current_pillow(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow is unavailable")
        import base64
        import io
        source = Image.new("RGB", (2560, 1280), "blue")
        encoded = app.image_to_base64_jpeg(source)
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as result:
            self.assertEqual(result.size, (1280, 640))
            self.assertEqual(result.format, "JPEG")

    def test_audio_close_is_attempted_even_if_stop_fails(self):
        device = mock.Mock()
        device.stop.side_effect = RuntimeError("device disconnected")
        with mock.patch.object(app, "record_failure"):
            self.assertEqual(app._close_audio_stream(device), ["stop"])
        device.close.assert_called_once()

    def test_empty_audio_device_cannot_select_the_first_microphone(self):
        with mock.patch("sounddevice.query_devices") as devices:
            self.assertIsNone(app.find_device("  "))
            devices.assert_not_called()

    def test_installed_ollama_does_not_download_another_installer(self):
        with mock.patch.object(app, "ollama_is_running", side_effect=[False, True]), \
                mock.patch.object(app, "_ollama_exe", return_value="installed-ollama"), \
                mock.patch("shutil.which", return_value="installed-ollama"), \
                mock.patch.object(app, "ollama_model_exists", return_value=True), \
                mock.patch("urllib.request.urlretrieve") as download, \
                mock.patch("subprocess.Popen") as spawn, mock.patch.object(app.time, "sleep"):
            app.ollama_install_and_start(lambda _: None)
        download.assert_not_called()
        spawn.assert_called_once()
        if os.name == "nt":
            self.assertTrue(spawn.call_args.kwargs["creationflags"] & 0x08000000)

    def test_quit_is_idempotent_and_stops_tray_and_stream(self):
        with mock.patch.object(app, "load_settings", side_effect=lambda: dict(app._default_settings(), backend="demo")):
            gui = app.App()
        icon, stream = mock.Mock(), mock.Mock()
        closed = threading.Event()
        stream.close.side_effect = closed.set
        gui._tray_icon = icon
        with mock.patch.object(app, "stream", stream):
            try:
                gui._quit()
                gui._quit()
                self.assertTrue(closed.wait(2))
                icon.stop.assert_called_once()
                stream.stop.assert_called_once()
                stream.close.assert_called_once()
            finally:
                gui._quit()

    def test_settings_drains_audio_and_preserves_workspace_content(self):
        import numpy as np

        settings = dict(app._default_settings(), backend="demo", transcription="local")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(app, "load_settings", return_value=settings), \
                mock.patch.object(app, "save_settings"), \
                mock.patch.object(app, "find_device", return_value=0), \
                mock.patch.object(app, "faster_whisper_installed", return_value=True), \
                mock.patch.object(app, "transcribe_local", return_value="Final audio survived."), \
                mock.patch("sounddevice.InputStream") as input_stream, \
                mock.patch("copilot_core.vision_capture.CaptureController.probe", return_value=False):
            gui = app.App(support_state_file=Path(folder) / "usage.json")
            try:
                gui._launch(settings)
                workspace = gui.current
                workspace.append_message("Copilot", "Earlier answer.", "ai")
                workspace.hud.pin()
                workspace._latest_notes = "Earlier meeting notes."
                workspace._manual_entry.delete("1.0", "end")
                workspace._manual_entry.insert("1.0", "Keep this draft")
                workspace._input_has_placeholder = False
                workspace.toggle_listening()
                callback = input_stream.call_args.kwargs["callback"]
                callback(np.full((4000, 1), 0.2, dtype=np.float32), 4000, None, None)
                workspace.on_settings()
                self.assertIs(gui.current, workspace)
                self.assertTrue(workspace._audio_is_finishing())

                deadline = time.monotonic() + 5
                while gui.current is workspace and time.monotonic() < deadline:
                    gui.root.update()
                    time.sleep(0.01)
                self.assertIsInstance(gui.current, app.SetupScreen)
                gui.current._launch()
                restored = gui.current
                self.assertIsInstance(restored, app.OverlayScreen)
                self.assertEqual(app.get_transcript_lines(), ["Final audio survived."])
                self.assertIn("Final audio survived.", restored.chat.get("1.0", "end"))
                self.assertEqual(restored._latest_notes, "Earlier meeting notes.")
                self.assertTrue(restored.hud.pinned)
                self.assertIn("Earlier answer.", restored.hud.answers[0].markdown())
                self.assertEqual(restored._manual_entry.get("1.0", "end-1c"), "Keep this draft")
            finally:
                gui._quit()

    @unittest.skipUnless(sys.platform == "win32", "Windows system tray")
    def test_failed_tray_icon_restores_the_window(self):
        with mock.patch.object(app, "load_settings", side_effect=lambda: dict(app._default_settings(), backend="demo")):
            gui = app.App()
        backend = mock.Mock()
        backend.Icon.return_value.run.side_effect = RuntimeError("tray unavailable")
        try:
            with mock.patch.object(app, "_TRAY_AVAILABLE", True), \
                    mock.patch.object(app, "pystray", backend, create=True), \
                    mock.patch.object(app, "_PILImage", mock.Mock(), create=True), \
                    mock.patch.object(app, "record_failure"):
                gui._minimize_to_tray()
                deadline = time.monotonic() + 2
                while not getattr(gui, "_tray_failed", False) and time.monotonic() < deadline:
                    gui.root.update()
                    time.sleep(.01)
                self.assertTrue(gui._tray_failed)
                self.assertNotEqual(gui.root.state(), "withdrawn")
        finally:
            gui._quit()

    def test_installer_ignores_callbacks_after_close(self):
        installer = setup.SetupApp()
        callbacks = []
        worker = threading.Thread(target=lambda: installer._post(lambda: callbacks.append("stale")))
        worker.start()
        worker.join()
        installer._close()
        installer._close()
        self.assertEqual(callbacks, [])

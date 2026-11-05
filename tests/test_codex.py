import os
import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import zoom_copilot as app
from copilot_core.answer_schema import parse_answer
from copilot_core.codex_backend import CodexService
from copilot_core.codex_client import Cancelled, CodexClient, CodexError, find_codex
from copilot_core.processes import OwnedProcess


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.service = CodexService()
        self.owners = []
        peer = Path(__file__).with_name("fake_codex_server.py")
        def factory(_command, **kwargs):
            owner = OwnedProcess([sys.executable, str(peer)], **kwargs)
            self.owners.append(owner)
            return owner
        self.spawn = mock.patch("copilot_core.codex_client.OwnedProcess", side_effect=factory)
        self.find = mock.patch("copilot_core.codex_backend.find_codex", return_value="test-codex")
        self.spawn.start()
        self.find.start()
        self.settings = {"codex_timeout": 5, "vision_mode": "manual"}

    def tearDown(self):
        self.service.close()
        self.spawn.stop()
        self.find.stop()
        for owner in self.owners:
            self.assertIsNotNone(owner.process.poll(), "owned process was not reaped")

    def test_real_backend_dispatch_uses_codex_without_requests_package(self):
        settings = app._coerce_settings({"backend": "codex"})
        with mock.patch("copilot_core.codex_backend.SERVICE.answer", return_value="ok") as answer, mock.patch.object(app, "requests", None):
            self.assertEqual(app.ask_ai([{"role": "user", "content": "hello"}], settings), "ok")
        answer.assert_called_once()
        self.assertTrue(app.backend_supports_vision(settings))

    def test_detection_does_not_read_or_expose_credentials(self):
        status = self.service.status(self.settings)
        self.assertTrue(status.installed and status.authenticated and status.available and status.vision)
        self.assertEqual(status.model, "test-model")

    def test_missing_installation(self):
        with mock.patch("copilot_core.codex_backend.find_codex", return_value=None):
            self.assertFalse(self.service.status(self.settings).installed)

    def test_missing_authentication(self):
        with mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": "unauthenticated"}):
            status = self.service.status(self.settings)
            self.assertTrue(status.installed)
            self.assertFalse(status.authenticated or status.available)
            with self.assertRaisesRegex(CodexError, "not authenticated"):
                self.service.answer([], self.settings, "test")

    def test_model_selection_and_vision_capability(self):
        with mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": "text-only"}):
            self.assertFalse(self.service.status(self.settings).vision)
            with self.assertRaisesRegex(CodexError, "does not support images"):
                self.service.answer([], self.settings, "test", image="image")
        with self.assertRaisesRegex(CodexError, "unavailable"):
            self.service.answer([], dict(self.settings, codex_model="missing"), "test")

    def test_final_events_before_rpc_response_are_retained(self):
        raw = self.service.answer([{"role": "user", "content": "solve"}], self.settings, "test")
        self.assertEqual(parse_answer(raw).type, "math")
        self.assertEqual(parse_answer(raw).summary, "x = 6")

    def test_malformed_model_response_is_safe_fallback(self):
        with mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": "malformed"}):
            answer = parse_answer(self.service.answer([], self.settings, "test"))
            self.assertFalse(answer.structured)
            self.assertIn("bad JSON", answer.content)

    def test_vision_off_does_not_launch_process(self):
        with self.assertRaisesRegex(CodexError, "Vision is off"):
            self.service.answer([], {"vision_mode": "off"}, "test", image="image")
        self.assertEqual(self.owners, [])

    def test_server_exit_and_failed_turn(self):
        for mode in ("stopped", "failed"):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": mode}):
                with self.assertRaises(CodexError):
                    self.service.answer([], self.settings, "test")

    def test_timeout_reaps_process(self):
        with mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": "slow"}):
            with self.assertRaisesRegex(CodexError, "timed out"):
                self.service.answer([], dict(self.settings, codex_timeout=0.4), "test")

    def test_session_cancellation_and_service_shutdown(self):
        for stop_service in (False, True):
            active, done = threading.Event(), threading.Event()
            active.set()
            errors = []
            def worker():
                try:
                    self.service.answer([], self.settings, "test", active=active.is_set)
                except CodexError as exc:
                    errors.append(exc)
                finally:
                    done.set()
            with mock.patch.dict(os.environ, {"COPILOT_FAKE_CODEX": "slow"}):
                thread = threading.Thread(target=worker)
                thread.start()
                time.sleep(0.15)
                self.service.close() if stop_service else active.clear()
                self.assertTrue(done.wait(3))
                thread.join()
            self.assertTrue(errors)
            if not stop_service:
                self.assertIsInstance(errors[0], Cancelled)

    def test_cli_discovery_rejects_script_paths(self):
        self.assertIsNone(find_codex("C:/missing/codex.exe"))
        self.assertIsNone(find_codex(str(Path(__file__).with_name("fake_codex_server.cmd"))))

    def test_server_tool_requests_are_refused(self):
        client = CodexClient("test", str(Path(__file__).parent), timeout=2)
        try:
            client._events.put({"id": 70, "method": "item/commandExecution/requestApproval", "params": {}})
            client._events.put({"method": "test-notification"})
            with mock.patch.object(client, "send") as send:
                self.assertEqual(client.receive()["method"], "test-notification")
                self.assertIn("error", send.call_args.args[0])
        finally:
            client.close()


class DiscoveryTests(unittest.TestCase):
    def test_explicit_paths_accept_quotes_and_environment_variables(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex.exe"
            executable.touch()
            with mock.patch.dict(os.environ, {"COPILOT_TEST_CLI": str(executable)}):
                self.assertEqual(find_codex('  "$COPILOT_TEST_CLI"  '), str(executable.resolve()))

    @unittest.skipUnless(os.name == "nt", "Windows CLI installation locations")
    def test_explorer_launch_finds_managed_cli_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed = root / "OpenAI" / "Codex" / "bin"
            old = managed / "old" / "codex.exe"
            new = managed / "new" / "codex.exe"
            for path in (old, new, managed / "codex.exe"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            os.utime(old, (100, 100))
            os.utime(new, (200, 200))
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                    mock.patch("copilot_core.codex_client.shutil.which", return_value=None):
                self.assertEqual(find_codex(), str(new.resolve()))
                new.unlink()
                self.assertEqual(find_codex(), str(old.resolve()))
                self.assertIsNone(find_codex(str(managed / "missing.exe")))

    @unittest.skipUnless(os.name == "nt", "Windows CLI installation locations")
    def test_discovery_never_uses_desktop_gui_as_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gui = root / "Codex" / "Codex.exe"
            gui.parent.mkdir()
            gui.touch()
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": directory, "APPDATA": directory}), \
                    mock.patch("copilot_core.codex_client.Path.home", return_value=root), \
                    mock.patch("copilot_core.codex_client.shutil.which", return_value=None):
                self.assertIsNone(find_codex())

    @unittest.skipUnless(os.name == "nt", "Windows npm launcher")
    def test_npm_shim_is_invoked_through_node_without_a_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            script.parent.mkdir(parents=True)
            script.touch()
            (root / "npm" / "codex.cmd").touch()
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": directory, "APPDATA": directory}), \
                    mock.patch("copilot_core.codex_client.Path.home", return_value=root), \
                    mock.patch("copilot_core.codex_client.shutil.which", side_effect=lambda n: "node.exe" if n == "node.exe" else None):
                self.assertEqual(find_codex(), ("node.exe", str(script)))


class ProcessTests(unittest.TestCase):
    def test_shutdown_is_idempotent_and_reaps_child(self):
        owner = OwnedProcess([sys.executable, "-c", "import time; time.sleep(30)"])
        owner.close()
        owner.close()
        self.assertIsNotNone(owner.process.poll())

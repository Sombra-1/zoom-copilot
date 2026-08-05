import queue
import sys
import threading
import time
import types
import unittest
from unittest import mock

import numpy as np

import zoom_copilot as copilot


class _Button:
    def config(self, **_kwargs):
        return None


class _FakeOverlay:
    s = {
        "device_name": "CABLE Output",
        "backend": "demo",
        "transcription": "local",
    }
    toggle_btn = _Button()

    def __init__(self):
        self.messages = []
        self.statuses = []

    def append_message(self, *message):
        self.messages.append(message)

    def set_status(self, *status):
        self.statuses.append(status)

    def update_stats(self):
        return None


class RuntimeTests(unittest.TestCase):
    def tearDown(self):
        copilot._end_listen_session()
        copilot._end_screen_session()
        copilot.stream = None

    def test_new_listen_generation_invalidates_previous_workers(self):
        first = copilot._begin_listen_session()
        second = copilot._begin_listen_session()
        self.assertFalse(copilot._listen_session_active(first))
        self.assertTrue(copilot._listen_session_active(second))

    def test_new_screen_generation_invalidates_previous_workers(self):
        first = copilot._begin_screen_session()
        second = copilot._begin_screen_session()
        self.assertFalse(copilot._screen_session_active(first))
        self.assertTrue(copilot._screen_session_active(second))

    def test_audio_processor_preserves_queue_order(self):
        generation = copilot._begin_listen_session()
        work = queue.Queue()
        work.put(np.array([1], dtype=np.float32))
        work.put(np.array([2], dtype=np.float32))
        processed = []

        def record(audio, _settings, _gui, _generation):
            processed.append(int(audio[0]))

        with mock.patch.object(copilot, "process_audio", side_effect=record):
            worker = threading.Thread(
                target=copilot.audio_process_loop,
                args=({}, object(), generation, work),
                daemon=True,
            )
            worker.start()
            deadline = time.time() + 2
            while len(processed) < 2 and time.time() < deadline:
                time.sleep(0.01)
            copilot._end_listen_session()
            worker.join(timeout=1.2)

        self.assertEqual(processed, [1, 2])

    def test_audio_start_failure_rolls_back_listening_state(self):
        class BrokenSoundDevice(types.ModuleType):
            def query_devices(self):
                return [{"name": "CABLE Output", "max_input_channels": 1}]

            class InputStream:
                def __init__(self, **_kwargs):
                    raise RuntimeError("simulated audio backend failure")

        fake_module = BrokenSoundDevice("sounddevice")
        overlay = _FakeOverlay()
        with mock.patch.dict(sys.modules, {"sounddevice": fake_module}):
            copilot.OverlayScreen._go_live(overlay)

        self.assertFalse(copilot._listen_event.is_set())
        self.assertTrue(any("Could not start audio capture" in row[1]
                            for row in overlay.messages))

    def test_signature_verifier_accepts_valid_powershell_result(self):
        result = types.SimpleNamespace(
            returncode=0,
            stdout="Valid\n",
            stderr="",
        )
        with mock.patch("subprocess.run", return_value=result) as run:
            copilot._verify_windows_signature("OllamaSetup.exe")
        run.assert_called_once()

    def test_signature_verifier_rejects_invalid_powershell_result(self):
        result = types.SimpleNamespace(
            returncode=0,
            stdout="NotSigned\n",
            stderr="",
        )
        with mock.patch("subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "not valid"):
                copilot._verify_windows_signature("OllamaSetup.exe")


if __name__ == "__main__":
    unittest.main()

"""Verify cancellation and restart through the actual worker process and pipes."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from copilot_core.codex_client import Cancelled
from copilot_core.whisper_session import WhisperBusy, WhisperSession, cache_busy, model_maintenance


FAKE_DECODER = '''
import os
from pathlib import Path
import threading
from types import SimpleNamespace

class WhisperModel:
    def __init__(self, *_args, **_kwargs):
        marker = Path(os.environ["COPILOT_TEST_WHISPER_LOADS"])
        with marker.open("a", encoding="utf-8") as log:
            log.write(str(os.getpid()) + "\\n")

    def transcribe(self, audio, **_kwargs):
        if audio[0] > 0.75:
            Path(os.environ["COPILOT_TEST_WHISPER_STALLED"]).touch()
            threading.Event().wait()
        return [SimpleNamespace(text="Recovered local audio.")], None
'''


class WhisperSessionTests(unittest.TestCase):
    def wait_for(self, ready):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if ready():
                return
            time.sleep(0.02)
        self.fail("Expected Whisper process state did not arrive")

    def test_stalled_process_is_reaped_and_local_transcription_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "faster_whisper.py").write_text(FAKE_DECODER, encoding="utf-8")
            stalled, loads = folder / "stalled", folder / "loads.txt"
            with mock.patch.dict(os.environ, {"PYTHONPATH": directory,
                                             "COPILOT_TEST_WHISPER_STALLED": str(stalled),
                                             "COPILOT_TEST_WHISPER_LOADS": str(loads)}):
                session = WhisperSession()
                errors = []

                def block():
                    try:
                        session.transcribe(np.ones(4000, dtype=np.float32), "base", "en")
                    except Exception as exc:
                        errors.append(exc)

                thread = threading.Thread(target=block, daemon=True)
                thread.start()
                try:
                    self.wait_for(stalled.exists)
                    with self.assertRaises(WhisperBusy), model_maintenance():
                        pass
                finally:
                    session.close()
                    thread.join(6)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], Cancelled)
                self.wait_for(lambda: not cache_busy())

                next_session = WhisperSession()
                try:
                    chunk = np.full(4000, 0.5, dtype=np.float32)
                    for _ in range(2):
                        self.assertEqual(next_session.transcribe(chunk, "base", "en"), "Recovered local audio.")
                    process_ids = loads.read_text(encoding="utf-8").splitlines()
                    self.assertEqual(len(process_ids), 2)
                    self.assertNotEqual(*process_ids)
                finally:
                    next_session.close()
                    self.wait_for(lambda: not cache_busy())

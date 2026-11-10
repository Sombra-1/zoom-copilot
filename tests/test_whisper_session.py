"""Verify cancellation and restart through the actual worker process and pipes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from copilot_core.codex_client import Cancelled
from copilot_core.processes import OwnedProcess
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

MAINTENANCE_PROBE = '''
from copilot_core.whisper_session import WhisperBusy, model_maintenance
try:
    with model_maintenance():
        print("acquired")
except WhisperBusy:
    print("busy")
'''

LAUNCHER_PROBE = '''
import ctypes
import json
import os
from pathlib import Path
import sys
import wave

import numpy as np
from copilot_core.whisper_session import WhisperSession

report = {"interpreter": Path(sys.executable).name, "has_console": bool(ctypes.windll.kernel32.GetConsoleWindow())}
session = WhisperSession()
try:
    speech_path = os.environ.get("COPILOT_WHISPER_LAUNCHER_AUDIO")
    if speech_path:
        with wave.open(speech_path, "rb") as speech:
            assert (speech.getnchannels(), speech.getsampwidth(), speech.getframerate()) == (1, 2, 16000)
            audio = np.frombuffer(speech.readframes(speech.getnframes()), dtype="<i2").astype(np.float32) / 32768
    else:
        audio = np.full(4000, 0.5, dtype=np.float32)
    report["text"] = session.transcribe(audio, "tiny", "en")
except Exception as exc:
    report["error"] = str(exc)
finally:
    session.close()
staging = Path("report.pending")
staging.write_text(json.dumps(report), encoding="utf-8")
staging.replace("report.json")
'''


class WhisperSessionTests(unittest.TestCase):
    def wait_for(self, ready, timeout=8):
        deadline = time.monotonic() + timeout
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
                                             "HF_HUB_CACHE": str(folder / "cache"),
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
                    self.assertEqual(self.maintenance_probe(), "busy")
                finally:
                    session.close()
                    thread.join(6)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], Cancelled)
                self.wait_for(lambda: not cache_busy())
                self.assertEqual(self.maintenance_probe(), "acquired")

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

    def maintenance_probe(self):
        return subprocess.check_output([sys.executable, "-c", MAINTENANCE_PROBE], text=True, timeout=8).strip()

    @unittest.skipUnless(os.name == "nt", "Windows launcher")
    def test_native_launcher_round_trips_local_whisper_audio(self):
        repo = Path(__file__).resolve().parents[1]
        windowless_python = Path(sys.executable).with_name("pythonw.exe")
        self.assertTrue(windowless_python.is_file(), windowless_python)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            binary = shutil.copy2(repo / "Zoom Copilot.exe", folder)
            shutil.copy2(repo / "launch.pyw", folder)
            shutil.copytree(repo / "copilot_core", folder / "copilot_core", ignore=shutil.ignore_patterns("__pycache__"))
            # Exercise the real launcher and worker with a minimal application entry point.
            (folder / "zoom_copilot.py").write_text(LAUNCHER_PROBE, encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=directory, HF_HUB_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
            real_audio = env.get("COPILOT_WHISPER_LAUNCHER_AUDIO")
            if not real_audio:
                (folder / "faster_whisper.py").write_text(FAKE_DECODER, encoding="utf-8")
                env["HF_HUB_CACHE"] = str(folder / "cache")
                env["COPILOT_TEST_WHISPER_LOADS"] = str(folder / "loads.txt")
            owner = OwnedProcess([binary, "--python", str(windowless_python)], cwd=folder, env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                report_file = folder / "report.json"
                self.wait_for(report_file.is_file, timeout=30)
                report = json.loads(report_file.read_text(encoding="utf-8"))
            finally:
                owner.close()
            self.assertNotIn("error", report, report)
            self.assertEqual(report["interpreter"].lower(), "pythonw.exe")
            self.assertFalse(report["has_console"])
            if real_audio:
                self.assertIn("windows launcher", report["text"].lower(), report)
            else:
                self.assertEqual(report["text"], "Recovered local audio.")

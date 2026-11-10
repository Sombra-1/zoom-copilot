"""Exercise finishing recovery with synthetic input and a blocked decoder."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import types
import unittest
from unittest import mock

import numpy as np

import zoom_copilot as app
from copilot_core.ui_dispatch import UiDispatcher
from copilot_core.ui_theme import destroy_root


class SyntheticInput:
    def __init__(self, callback, **_options):
        self.callback = callback
        self.closed = False
        self.stop_gate = None
        self.stop_entered = threading.Event()

    def start(self):
        pass

    def stop(self):
        self.stop_entered.set()
        if self.stop_gate is not None:
            self.stop_gate.wait(5)

    def close(self):
        self.closed = True

    def emit(self, level, frames=16000):
        block = np.full((frames, 1), level, dtype=np.float32)
        self.callback(block, frames, None, None)


class AudioDrainRecoveryTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(destroy_root, self.root)
        self.root.withdraw()
        self.root._dispatcher = UiDispatcher(self.root)
        self.addCleanup(self.root._dispatcher.close)
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.release = threading.Event()
        self.decoder_entered = threading.Event()
        self.initial_threads = set(threading.enumerate())

        def decode(audio, *_args, **_kwargs):
            if audio[0] < 0.75:
                return "Earlier speech."
            self.decoder_entered.set()
            self.release.wait()
            return "Late speech from the abandoned session."

        sounddevice = types.ModuleType("sounddevice")
        sounddevice.InputStream = SyntheticInput
        sounddevice.query_devices = lambda: [{"name": "Synthetic input", "max_input_channels": 1}]
        stack.enter_context(mock.patch.dict(sys.modules, {"sounddevice": sounddevice}))
        stack.enter_context(mock.patch.object(app, "faster_whisper_installed", return_value=True))
        stack.enter_context(mock.patch.object(app, "transcribe_local", side_effect=decode))
        stack.enter_context(mock.patch.object(app, "ask_ai", return_value="Demo reply."))
        stack.enter_context(mock.patch.object(app.CaptureController, "probe", return_value=False))
        self.settings = dict(app._default_settings(), backend="demo", transcription="local",
                             device_name="Synthetic input", chunk_seconds=1)
        self.screen = app.OverlayScreen(self.root, self.settings, lambda: None)
        self.addCleanup(self.screen.destroy)
        self.addCleanup(self._stop_audio)
        with app._history_lock:
            app.conversation_history.clear()

    def _workers(self):
        return [worker for worker in threading.enumerate()
                if worker not in self.initial_threads and worker.name.startswith("copilot-audio-")]

    def _stop_audio(self):
        app._end_listen_session()
        if app.stream is not None:
            app._close_audio_stream(app.stream)
            app.stream = None
        self.release.set()
        for worker in self._workers():
            worker.join(timeout=2)
        with app._history_lock:
            app.conversation_history.clear()

    def _pump_until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("The audio recovery state did not arrive")

    def _begin_blocked_drain(self):
        self.screen.toggle_listening()
        stream = app.stream
        self.assertIsNotNone(stream)
        stream.emit(0.5)
        self._pump_until(lambda: app.get_transcript_lines() == ["Earlier speech."])
        stream.emit(1.0, frames=4000)
        self.screen.toggle_listening()
        self._pump_until(lambda: stream.closed and not app._audio_device_closing.is_set())
        self.assertTrue(self.screen._audio_is_finishing())
        self._pump_until(self.decoder_entered.is_set)
        decoder = next(worker for worker in self._workers()
                       if worker.name.startswith("copilot-audio-transcript-"))
        return decoder

    def _assert_recovered_transcript(self):
        self.assertFalse(app._listen_event.is_set())
        self.assertFalse(self.screen._audio_is_finishing())
        self.assertEqual(self.screen.toggle_btn.cget("state"), "normal")
        self.assertEqual(self.screen.toggle_btn.cget("text"), "Start listening")
        self.assertEqual(self.screen._notes_btn.cget("state"), "normal")
        lines = app.get_transcript_lines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "Earlier speech.")
        self.assertTrue(lines[1].startswith("[AUDIO GAP]"), lines[1])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recovered.md"
            with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(path)):
                self.screen.export_meeting_markdown()
            export = path.read_text(encoding="utf-8")
        self.assertIn("\n- " + "\n- ".join(lines), export)
        return lines

    def test_cancel_restores_export_and_fences_late_result_after_restart(self):
        dispatcher = self.root._dispatcher
        post = dispatcher.post
        delayed = []

        def hold_transcript_callbacks(callback):
            if threading.current_thread().name.startswith("copilot-audio-transcript-"):
                delayed.append(callback)
                return True
            return post(callback)

        with mock.patch.object(dispatcher, "post", side_effect=hold_transcript_callbacks):
            decoder = self._begin_blocked_drain()
        # Earlier speech was committed while its UI callback was still waiting.
        self.assertFalse(any(item["label"] == "Transcript" for item in self.screen._chat_items))
        self.assertEqual(self.screen.toggle_btn.cget("text"), "Cancel finishing")
        self.screen.toggle_btn.invoke()
        lines = self._assert_recovered_transcript()
        self.assertIn("canceled", lines[-1].lower())
        self.assertTrue(decoder.is_alive())
        for callback in delayed:
            callback()
        self.assertEqual([item["label"] for item in self.screen._chat_items
                          if item["kind"] == "them"], ["Transcript", "Audio gap"])

        # A fresh session can start while a stale, mocked decode is blocked.
        with mock.patch.object(app, "transcribe_local", return_value="Fresh speech."):
            self.screen.toggle_listening()
            new_stream = app.stream
            self.assertIsNotNone(new_stream)
            new_stream.emit(0.5)
            self._pump_until(lambda: app.get_transcript_lines() == lines + ["Fresh speech."])
            self.release.set()
            decoder.join(timeout=2)
            self.assertFalse(decoder.is_alive())
            self.root.update()
            self.assertIs(app.stream, new_stream)
            self.assertEqual(app.get_transcript_lines(), lines + ["Fresh speech."])
            self.assertFalse(any("Late speech" in item["text"] for item in self.screen._chat_items))

    def test_deadline_recovers_while_decoder_is_still_blocked(self):
        with mock.patch.object(app, "AUDIO_DRAIN_TIMEOUT_MS", 500):
            decoder = self._begin_blocked_drain()
            self._pump_until(lambda: not self.screen._audio_is_finishing())
        lines = self._assert_recovered_transcript()
        self.assertIn("timed out", lines[-1].lower())
        self.assertTrue(decoder.is_alive())
        self.assertFalse(self.release.is_set())

    def test_keyboard_action_cancels_finishing(self):
        self._begin_blocked_drain()
        self.screen.toggle_listening()
        self.assertIn("canceled", self._assert_recovered_transcript()[-1].lower())

    def test_device_query_failure_leaves_start_available(self):
        with mock.patch("sounddevice.query_devices", side_effect=OSError("Device disconnected")):
            self.screen.toggle_listening()
            self._pump_until(lambda: "Audio device unavailable" in self.screen.status_lbl.cget("text"))
        self.assertFalse(app._listen_event.is_set())
        self.assertEqual(self.screen.toggle_btn.cget("text"), "Start listening")
        self.assertTrue(any("Device disconnected" in row["text"] for row in self.screen._chat_items))

        self.screen.toggle_listening()
        self.assertTrue(app._listen_event.is_set())

    def test_exact_audio_input_beats_partial_name(self):
        devices = [{"name": "Monitor (Synthetic input)", "max_input_channels": 1},
                   {"name": "Synthetic input", "max_input_channels": 1}]
        with mock.patch("sounddevice.query_devices", return_value=devices):
            self.assertEqual(app.find_device("synthetic input"), 1)
            self.assertEqual(app.find_device("Monitor"), 0)

    def test_stop_drains_audio_while_driver_stop_is_blocked(self):
        self.screen.toggle_listening()
        device = app.stream
        self.assertIsNotNone(device)
        device.stop_gate = threading.Event()
        self.addCleanup(device.stop_gate.set)
        device.emit(0.5, frames=4000)
        self.screen.toggle_listening()
        self._pump_until(device.stop_entered.is_set)
        self._pump_until(lambda: not self.screen._audio_is_finishing())
        self.assertFalse(device.closed)
        self.assertEqual(app.get_transcript_lines(), ["Earlier speech."])
        self.screen.toggle_listening()
        self.assertIsNone(app.stream)
        self.assertTrue(any("reconnect an external audio device" in row["text"] for row in self.screen._chat_items))
        device.stop_gate.set()
        self._pump_until(lambda: device.closed and not app._audio_device_closing.is_set())

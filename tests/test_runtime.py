import os
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
        with copilot._history_lock:
            copilot.conversation_history.clear()

    def test_audio_errors_dispatch_stop_and_cannot_stop_a_new_session(self):
        for mode in ("missing-whisper", "missing-key", "forbidden"):
            with self.subTest(mode=mode):
                callbacks = []
                gui = types.SimpleNamespace(_post=callbacks.append, _stop=mock.Mock(),
                                            append_message=mock.Mock(), set_status=mock.Mock())
                settings = {"transcription": "local" if mode == "missing-whisper" else "groq",
                            "groq_key": "" if mode == "missing-key" else "test-key"}
                generation = copilot._begin_listen_session()
                with mock.patch.object(copilot, "faster_whisper_installed", return_value=False), \
                        mock.patch.object(copilot, "transcribe_groq", side_effect=RuntimeError("403 Forbidden")):
                    copilot.process_audio(np.ones(4000, dtype=np.float32), settings, gui, generation)
                gui._stop.assert_not_called()
                if mode == "missing-whisper":
                    callbacks[0]()
                    gui._stop.assert_called_once()
                    gui._stop.reset_mock()
                copilot._begin_listen_session()
                for callback in callbacks:
                    callback()
                gui._stop.assert_not_called()

    def test_new_listen_generation_invalidates_previous_workers(self):
        first = copilot._begin_listen_session()
        second = copilot._begin_listen_session()
        self.assertFalse(copilot._listen_session_active(first))
        self.assertTrue(copilot._listen_session_active(second))

    def test_spoken_question_uses_current_screen_when_vision_is_enabled(self):
        gui = mock.Mock()
        gui._active_token.return_value = lambda: True
        generation = copilot._begin_listen_session()
        settings = dict(copilot._default_settings(), backend="codex", transcription="local",
                        vision_mode="periodic", vision_target="desktop")
        with mock.patch.object(copilot, "faster_whisper_installed", return_value=True), \
                mock.patch.object(copilot, "transcribe_local", return_value="What can you see on screen?"), \
                mock.patch.object(copilot, "ask_ai") as text:
            copilot.process_audio(np.ones(4000, dtype=np.float32), settings, gui, generation)
            gui.analyze_screen.assert_called_once()
            self.assertEqual(gui.analyze_screen.call_args.kwargs["settings"]["vision_question"],
                             "What can you see on screen?")
            text.assert_not_called()

    def test_new_screen_generation_invalidates_previous_workers(self):
        first = copilot._begin_screen_session()
        second = copilot._begin_screen_session()
        self.assertFalse(copilot._screen_session_active(first))
        self.assertTrue(copilot._screen_session_active(second))

    def test_audio_processor_preserves_queue_order(self):
        generation = copilot._begin_listen_session()
        work = queue.Queue()
        work.put(copilot.TranscriptionJob(np.array([1], dtype=np.float32)))
        work.put(copilot.TranscriptionJob(np.array([2], dtype=np.float32)))
        processed = []

        def record(audio, _settings, _gui, _generation, _answers, _capture, **_options):
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

    def test_transcription_continues_while_spoken_answer_is_blocked(self):
        generation = copilot._begin_listen_session()
        settings = dict(copilot._default_settings(), backend="demo", transcription="local")
        work, answers = queue.Queue(), queue.Queue(maxsize=1)
        entered, release, heard_third = threading.Event(), threading.Event(), threading.Event()
        gui = mock.Mock(spec=["append_message", "set_status", "update_stats", "_post"])
        gui._post.side_effect = lambda callback: callback()
        gui.append_message.side_effect = lambda label, text, kind: (
            heard_third.set() if label == "Transcript" and text == "Third question?" else None
        )

        def slow_answer(*_args, **_kwargs):
            entered.set()
            release.wait(5)
            return "An answer from the stopped session"

        worker = threading.Thread(target=copilot.audio_process_loop,
                                  args=(settings, gui, generation, work, answers), daemon=True)
        inference = threading.Thread(target=copilot.audio_answer_loop,
                                     args=(gui, generation, answers), daemon=True)
        with mock.patch.object(copilot, "faster_whisper_installed", return_value=True), \
                mock.patch.object(copilot, "transcribe_local", side_effect=["First question?", "Second question?", "Third question?"]), \
                mock.patch.object(copilot, "ask_ai", side_effect=slow_answer):
            worker.start()
            inference.start()
            try:
                work.put(copilot.TranscriptionJob(np.ones(4000, dtype=np.float32)))
                self.assertTrue(entered.wait(3))
                for _ in range(2):
                    work.put(copilot.TranscriptionJob(np.ones(4000, dtype=np.float32)))
                self.assertTrue(heard_third.wait(3))
                work.join()
                self.assertEqual(copilot.get_transcript_lines(),
                                 ["First question?", "Second question?", "Third question?"])
                self.assertEqual(answers.queue[0][0], "Third question?")
            finally:
                copilot._end_listen_session()
                release.set()
                worker.join(2)
                inference.join(2)
        self.assertFalse(any(call.args[0] == "Copilot" for call in gui.append_message.call_args_list))

    def test_stop_drains_partial_audio_after_ordered_backlog_gap(self):
        generation = copilot._begin_listen_session()
        capture, work = copilot.AudioInput(), queue.Queue(maxsize=1)
        settings = dict(copilot._default_settings(), transcription="local", chunk_seconds=1)
        gui = mock.Mock(spec=["append_message", "set_status", "update_stats", "_post", "_finish_audio_stop"])
        backlog_ready, finished = threading.Event(), threading.Event()

        def post(callback):
            callback()
            return True

        def stats():
            if gui.update_stats.call_count == 2:
                backlog_ready.set()

        def finish(*_args):
            copilot._end_listen_session()
            finished.set()

        gui._post.side_effect = post
        gui.update_stats.side_effect = stats
        gui._finish_audio_stop.side_effect = finish
        block = np.ones((16000, 1), dtype=np.float32)
        capture.callback(block, len(block), None, None)
        capture.callback(block, len(block), None, None)
        collector = threading.Thread(target=copilot.transcribe_loop,
                                     args=(settings, gui, generation, capture, work), daemon=True)
        decoder = threading.Thread(target=copilot.audio_process_loop,
                                   args=(settings, gui, generation, work, None, capture), daemon=True)
        with mock.patch.object(copilot, "faster_whisper_installed", return_value=True), \
                mock.patch.object(copilot, "transcribe_local", side_effect=["Earlier speech", "Yes"]) as transcribe, \
                mock.patch.object(copilot, "ask_ai") as ask:
            collector.start()
            try:
                self.assertTrue(backlog_ready.wait(3))
                self.assertEqual(copilot.get_transcript_lines(), [])
                self.assertEqual(work.qsize(), 1)
                # Stop with the queue full and a tail shorter than 200 ms.
                capture.callback(block[:2000], 2000, None, None)
                capture.closed.set()
                decoder.start()
                self.assertTrue(finished.wait(3))
                self.assertEqual([len(call.args[0]) for call in transcribe.call_args_list], [16000, 2000])
                self.assertEqual([call.args[0] for call in gui.append_message.call_args_list],
                                 ["Transcript", "Audio gap", "Transcript"])
                first, gap, last = copilot.get_transcript_lines()
                self.assertEqual((first, last), ("Earlier speech", "Yes"))
                self.assertIn("backlog dropped audio (about 1.0 s)", gap)
                ask.assert_not_called()
            finally:
                copilot._end_listen_session()
                collector.join(2)
                if decoder.ident is not None:
                    decoder.join(2)

    def test_last_dropped_input_block_produces_a_trailing_gap(self):
        generation = copilot._begin_listen_session()
        capture, work = copilot.AudioInput(), queue.Queue(maxsize=2)
        capture.blocks = queue.Queue(maxsize=1)
        block = np.ones((4000, 1), dtype=np.float32)
        capture.callback(block, len(block), None, None)
        capture.callback(block, len(block), None, types.SimpleNamespace(input_overflow=True))
        capture.closed.set()
        copilot.transcribe_loop({"chunk_seconds": 1}, mock.Mock(), generation, capture, work)
        speech, gap = work.get_nowait(), work.get_nowait()
        self.assertEqual(len(speech.audio), len(block))
        self.assertFalse(speech.gaps)
        self.assertIsNone(gap.audio)
        self.assertEqual(gap.gaps, (("Audio input buffer overflowed", 4000),
                                    ("The audio device reported an input overflow", 0)))

    def test_speech_pause_enqueues_audio_before_the_configured_maximum(self):
        generation = copilot._begin_listen_session()
        capture, work = copilot.AudioInput(), queue.Queue()
        settings = dict(copilot._default_settings(), chunk_seconds=8)
        collector = threading.Thread(target=copilot.transcribe_loop,
                                     args=(settings, mock.Mock(), generation, capture, work), daemon=True)
        collector.start()
        try:
            speech = np.full((1600, 1), 0.25, dtype=np.float32)
            silence = np.zeros_like(speech)
            for _ in range(18):
                capture.callback(speech, len(speech), None, None)
            for _ in range(4):
                capture.callback(silence, len(silence), None, None)
            segment = work.get(timeout=3)
            self.assertFalse(capture.closed.is_set())
            np.testing.assert_array_equal(segment.audio, np.r_[np.tile(speech[:, 0], 18), np.zeros(6400)])
            self.assertFalse(segment.gaps)
        finally:
            copilot._end_listen_session()
            collector.join(2)

    def test_silero_filters_noise_and_overlaps_quiet_speech_across_a_cut(self):
        generation = copilot._begin_listen_session()
        capture, work = copilot.AudioInput(), queue.Queue()
        settings = dict(copilot._default_settings(), chunk_seconds=2, silero_vad=True, vad_sensitivity=0.7)
        gui = mock.Mock()

        def predict(window):
            frames = window.reshape(-1, 512)
            return np.where(np.isclose(frames[:, 0], 0.004), 0.4, 0.05)

        faster_whisper = types.ModuleType("faster_whisper")
        vad = types.ModuleType("faster_whisper.vad")
        vad.get_vad_model = lambda: predict
        noise = np.full((1600, 1), 0.2, dtype=np.float32)
        quiet = np.full((1600, 1), 0.004, dtype=np.float32)
        for block in [noise] * 20 + [quiet] * 20 + [quiet] * 2:
            capture.callback(block, len(block), None, None)
        capture.close_input()
        with mock.patch.dict(sys.modules, {"faster_whisper": faster_whisper, "faster_whisper.vad": vad}):
            copilot.transcribe_loop(settings, gui, generation, capture, work)

        first, tail = work.get_nowait(), work.get_nowait()
        self.assertTrue(work.empty())
        self.assertTrue(first.speech_detected and tail.speech_detected)
        self.assertEqual(first.overlap_samples, 0)
        self.assertEqual(tail.overlap_samples, 5120)
        np.testing.assert_array_equal(first.audio, np.tile(quiet[:, 0], 20))
        np.testing.assert_array_equal(tail.audio, np.r_[first.audio[-5120:], np.tile(quiet[:, 0], 2)])

    def test_groq_overlap_removes_words_that_end_before_the_boundary(self):
        with mock.patch("urllib.request.urlopen") as request:
            response = request.return_value.__enter__.return_value
            response.read.return_value = (b'{"text":"old crossing new","words":['
                                          b'{"word":"old","end":0.2},{"word":"crossing","end":0.4},'
                                          b'{"word":"new","end":0.8}]}')
            text = copilot.transcribe_groq(np.ones(16000, dtype=np.float32), "test-key", overlap_samples=5120)
        self.assertEqual(text, "crossing new")
        self.assertIn(b'\r\n\r\nverbose_json\r\n', request.call_args.args[0].data)
        self.assertIn(b'name="timestamp_granularities[]"\r\n\r\nword\r\n', request.call_args.args[0].data)

    def test_groq_auto_language_omits_the_language_field(self):
        audio = np.zeros(4000, dtype=np.float32)
        with mock.patch("urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"text":"Detected speech"}'
            self.assertEqual(copilot.transcribe_groq(audio, "test-key", language="auto"), "Detected speech")
            self.assertNotIn(b'name="language"', request.call_args.args[0].data)
            copilot.transcribe_groq(audio, "test-key", language=" EN ")
            self.assertIn(b'name="language"\r\n\r\nen\r\n', request.call_args.args[0].data)

    def test_queued_vision_prompt_is_cancelled_after_scope_change(self):
        gui = mock.Mock()
        gui._vision_epoch = 2
        copilot._answer_spoken_prompt(gui, "What is on screen?", [], {"vision_mode": "manual"}, lambda: True, 1)
        gui.analyze_screen.assert_not_called()

    def test_groq_timeout_retries_once_and_cancelled_session_does_not_retry(self):
        audio = np.ones(4000, dtype=np.float32)
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError) as request, \
                mock.patch.object(copilot.time, "sleep"):
            with self.assertRaises(TimeoutError):
                copilot.transcribe_groq(audio, "test-key")
            self.assertEqual(request.call_count, 2)
            self.assertTrue(all(call.kwargs["timeout"] == 8 for call in request.call_args_list))
            request.reset_mock()
            with self.assertRaises(copilot.Cancelled):
                copilot.transcribe_groq(audio, "test-key", active=mock.Mock(side_effect=[True, False]))
            self.assertEqual(request.call_count, 1)

    def test_whisper_cache_uses_hub_override_then_hf_home(self):
        with mock.patch.dict(os.environ, {"HF_HOME": "test-home", "HUGGINGFACE_HUB_CACHE": "legacy",
                                         "HF_HUB_CACHE": "explicit"}, clear=True):
            self.assertEqual(copilot._get_whisper_cache_dir(), os.path.abspath("explicit/zoom-copilot-v2.1"))
            del os.environ["HF_HUB_CACHE"]
            self.assertEqual(copilot._get_whisper_cache_dir(), os.path.abspath("legacy/zoom-copilot-v2.1"))
            del os.environ["HUGGINGFACE_HUB_CACHE"]
            self.assertEqual(copilot._get_whisper_cache_dir(), os.path.abspath("test-home/hub/zoom-copilot-v2.1"))

    def test_long_meeting_notes_feed_all_transcript_batches(self):
        lines = [f"SEGMENT-{number:03} " + "Context for this meeting. " * 6 for number in range(180)]
        with mock.patch.object(copilot, "_call_ai_backend", return_value="## Decisions\n- Earlier decision") as backend:
            copilot.ask_meeting_notes(lines, {"backend": "demo"})
        batches = [call.args[0] for call in backend.call_args_list]
        self.assertGreater(len(batches), 1)
        self.assertIn("Earlier decision", batches[1][0]["content"])
        self.assertEqual("".join(batch[-1]["content"].removeprefix("[TRANSCRIPT_LOG]\n") for batch in batches),
                         "\n".join(f"- {line}" for line in lines))

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

"""Classify 16 kHz capture in bounded batches with bundled Silero VAD."""
import numpy as np


class SileroSpeech:
    FRAME = 512
    BATCH = 8 * FRAME
    CONTEXT = 16 * FRAME

    def __init__(self, sensitivity):
        from faster_whisper.vad import get_vad_model

        self._model = get_vad_model()
        self._threshold = 1 - sensitivity
        self.reset()

    def reset(self, context=()):
        self._pending = np.empty(0, dtype=np.float32)
        self._context = np.asarray(context, dtype=np.float32)[-self.CONTEXT:]
        self.heard_speech = False
        self.quiet_samples = 0

    def observe(self, samples, *, flush=False):
        self._pending = np.concatenate((self._pending, np.asarray(samples, dtype=np.float32).reshape(-1)))
        count = len(self._pending)
        if not count or (count < self.BATCH and not flush):
            return

        size = count if flush else count // self.FRAME * self.FRAME
        fresh = self._pending[:size]
        self._pending = self._pending[size:]
        fresh = np.pad(fresh, (0, (-size) % self.FRAME))
        window = np.concatenate((self._context, fresh))
        scores = np.asarray(self._model(window)).reshape(-1)
        if len(scores) != len(window) // self.FRAME or not np.isfinite(scores).all():
            raise RuntimeError("Unexpected Silero speech probabilities")
        fresh_frames = len(fresh) // self.FRAME
        speech = np.flatnonzero(scores[-fresh_frames:] >= self._threshold)
        if speech.size:
            self.heard_speech = True
            self.quiet_samples = max(0, size - (int(speech[-1]) + 1) * self.FRAME)
        else:
            self.quiet_samples += size
        self._context = window[-self.CONTEXT:]

"""Internal Local Whisper subprocess protocol over private stdin/stdout."""
import base64
from contextlib import ExitStack
import json
import sys

from .whisper_session import MAX_AUDIO_BYTES, MAX_REQUEST, WhisperBusy, cache_lease, whisper_cache_directory


def serve(cache):
    import numpy as np
    from faster_whisper import WhisperModel

    model = None
    model_name = None
    cache_held = False
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not line or len(line) > MAX_REQUEST or not line.endswith(b"\n"):
            return
        try:
            request = json.loads(line)
            raw = base64.b64decode(request["audio"], validate=True)
            if not raw or len(raw) > MAX_AUDIO_BYTES or len(raw) % 4:
                raise ValueError("Invalid audio buffer")
            requested = request["model"]
            if requested not in ("tiny", "base", "small", "medium", "large-v2"):
                raise ValueError("Unknown model")
            if not cache_held:
                cache.enter_context(cache_lease())
                cache_held = True
            if model_name != requested:
                model = WhisperModel(requested, device="cpu", compute_type="int8", download_root=whisper_cache_directory())
                model_name = requested
            language = request["language"]
            language = language if language and language != "auto" else None
            overlap = request.get("overlap_samples", 0)
            if not isinstance(overlap, int) or not 0 <= overlap < len(raw) // 4:
                raise ValueError("Invalid overlap")
            segments, _ = model.transcribe(np.frombuffer(raw, dtype="<f4").copy(),
                                           language=language, beam_size=5, word_timestamps=bool(overlap))
            parts = []
            for segment in segments:
                if overlap and segment.words:
                    parts.append("".join(word.word for word in segment.words if word.end * 16000 > overlap))
                else:
                    parts.append(segment.text)
            response = {"text": " ".join(part.strip() for part in parts if part.strip())[:10000]}
        except WhisperBusy as exc:
            response = {"error": str(exc), "busy": True}
        except Exception as exc:
            response = {"error": f"Local Whisper failed ({type(exc).__name__}). Check the model in Audio & transcript."}
        sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    with ExitStack() as cache:
        serve(cache)

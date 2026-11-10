"""Internal Local Whisper subprocess protocol over private stdin/stdout."""
import base64
import json
import sys

from .whisper_session import MAX_AUDIO_BYTES, MAX_REQUEST


def main():
    import numpy as np
    from faster_whisper import WhisperModel

    model = None
    model_name = None
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
            if model_name != requested:
                model = WhisperModel(requested, device="cpu", compute_type="int8")
                model_name = requested
            language = request["language"]
            language = language if language and language != "auto" else None
            segments, _ = model.transcribe(np.frombuffer(raw, dtype="<f4").copy(),
                                           language=language, beam_size=5)
            response = {"text": " ".join(segment.text for segment in segments).strip()[:10000]}
        except Exception as exc:
            response = {"error": f"Local Whisper failed ({type(exc).__name__}). Check the model in Audio & transcript."}
        sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()

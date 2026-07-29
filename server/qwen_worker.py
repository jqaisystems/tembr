"""Qwen3-TTS worker — runs in its own venv (.venv-qwen) because qwen-tts and
chatterbox-tts pin conflicting transformers versions. The main API spawns and
manages this process; it listens on localhost only.

  .venv-qwen\\Scripts\\python.exe qwen_worker.py   (port 8101)
"""
import os
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(BASE / "models"))
os.environ.setdefault("TMP", str(BASE / ".cache" / "tmp"))
os.environ.setdefault("TEMP", str(BASE / ".cache" / "tmp"))

import soundfile as sf  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

app = FastAPI(title="Qwen3-TTS worker")
_model = None
_lock = threading.Lock()
_state = {"status": "loading"}


def _load() -> None:
    global _model
    with _lock:
        if _model is None:
            from qwen_tts import Qwen3TTSModel

            _model = Qwen3TTSModel.from_pretrained(MODEL_ID, device_map="cuda:0")
            _state["status"] = "ready"


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=_load, daemon=True).start()


class SynthesizeRequest(BaseModel):
    text: str
    language: str  # Qwen language name, e.g. "Portuguese"
    ref_audio: str  # path to reference wav
    ref_text: str  # transcript of the reference
    out_path: str  # where to write the wav


@app.get("/health")
def health():
    return _state


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    _load()  # no-op when already loaded; blocks until ready on first call
    try:
        wavs, sr = _model.generate_voice_clone(
            text=req.text,
            language=req.language,
            ref_audio=req.ref_audio,
            ref_text=req.ref_text,
        )
    except Exception as e:
        raise HTTPException(500, f"qwen synthesis failed: {e}")
    sf.write(req.out_path, wavs[0], sr)
    duration = len(wavs[0]) / sr
    return {"out_path": req.out_path, "duration_s": duration}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8101, log_level="warning")

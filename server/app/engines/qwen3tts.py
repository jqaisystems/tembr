"""Qwen3-TTS engine — proxies to the worker process in .venv-qwen (see
server/qwen_worker.py for why it is isolated). Chosen for Portuguese:
its pt sounds European, Chatterbox's leans Brazilian."""
import subprocess
import sys
import time
from pathlib import Path

import httpx
# Imported at module load (main thread, before any worker threads exist): a lazy
# import inside clone() can race the startup eager-load thread's own torchaudio
# import, leaving the module half-initialized ("cannot import name 'GriffinLim'").
import torchaudio  # noqa: F401  (torch first is fine; ctranslate2 loads later)

from ..config import BASE_DIR
from .base import BaseEngine

WORKER_URL = "http://127.0.0.1:8101"
WORKER_SCRIPT = BASE_DIR / "server" / "qwen_worker.py"
WORKER_PYTHON = BASE_DIR / "server" / ".venv-qwen" / "Scripts" / "python.exe"

# code -> Qwen language name
QWEN_LANGUAGES = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

MIN_REFERENCE_SECONDS = 5.0

# ref_text transcriptions per reference file, so whisper runs once per voice.
_ref_text_cache: dict[str, str] = {}


class Qwen3TTSEngine(BaseEngine):
    name = "qwen3tts"
    languages = list(QWEN_LANGUAGES)

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def _worker_alive(self) -> bool:
        try:
            return httpx.get(f"{WORKER_URL}/health", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def load(self) -> None:
        if self._worker_alive():
            return
        if not WORKER_PYTHON.exists():
            raise RuntimeError("qwen venv missing — see server/.venv-qwen")
        self._proc = subprocess.Popen(
            [str(WORKER_PYTHON), str(WORKER_SCRIPT)],
            cwd=str(WORKER_SCRIPT.parent),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        for _ in range(30):
            time.sleep(1)
            if self._worker_alive():
                print("[qwen3tts] worker up on :8101")
                return
        raise RuntimeError("qwen worker did not come up on :8101")

    def clone(self, reference_wavs: list[Path]) -> dict:
        if not reference_wavs:
            raise ValueError("At least one reference recording is required.")
        primary = reference_wavs[0]
        info = torchaudio.info(str(primary))
        seconds = info.num_frames / info.sample_rate
        if seconds < MIN_REFERENCE_SECONDS:
            raise ValueError(
                f"Reference audio is {seconds:.1f}s. It needs at least "
                f"{MIN_REFERENCE_SECONDS:.0f}s of clean speech."
            )
        key = str(primary)
        if key not in _ref_text_cache:
            # Qwen cloning needs the reference transcript; whisper provides it.
            from ..api.studio import _get_whisper

            segments, _info = _get_whisper().transcribe(key, vad_filter=True)
            _ref_text_cache[key] = " ".join(s.text.strip() for s in segments)
        return {
            "audio_prompt_path": key,
            "ref_text": _ref_text_cache[key],
            "reference_seconds": round(seconds, 1),
        }

    def synthesize(
        self,
        profile: dict | None,
        text: str,
        language: str,
        out_path: Path,
        options: dict | None = None,
    ) -> float:
        if language not in QWEN_LANGUAGES:
            raise ValueError(f"Language '{language}' not supported by qwen3tts.")
        if not profile or not profile.get("audio_prompt_path"):
            raise ValueError("qwen3tts needs a cloned voice. Pick one in Voices.")
        self.load()
        r = httpx.post(
            f"{WORKER_URL}/synthesize",
            json={
                "text": text,
                "language": QWEN_LANGUAGES[language],
                "ref_audio": profile["audio_prompt_path"],
                "ref_text": profile.get("ref_text", ""),
                "out_path": str(out_path),
            },
            timeout=600,
        )
        if r.status_code != 200:
            detail = r.json().get("detail", r.text) if r.content else r.text
            raise ValueError(str(detail))
        return float(r.json()["duration_s"])

    def unload(self) -> None:
        if self._proc:
            self._proc.terminate()
            self._proc = None

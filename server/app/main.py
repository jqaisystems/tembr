from . import config  # noqa: F401  — must be first: redirects HF/torch caches to E:
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import generate, health, outreach, profile, sites, studio, voices

app = FastAPI(title="Tembr", version="0.1.0")

# Local web UI (phase 2) will run on another localhost port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(voices.router)
app.include_router(generate.router)
app.include_router(studio.router)
app.include_router(outreach.router)
app.include_router(profile.router)
app.include_router(sites.router)


def _backfill_generation_names() -> None:
    """Name generations made before names existed, from their own text."""
    from .api.generate import name_from_text, unique_name

    for gen in db.list_generations(limit=100000):
        if not gen.get("name"):
            db.update_generation(gen["id"], name=unique_name(name_from_text(gen["text"])))


def _backfill_voice_qc() -> None:
    """Measure voices cloned before quality was recorded.

    Without this, every voice that predates the feature stays unrated, so it
    never shows a quality badge and is never offered a cleanup, which is
    exactly the library that needs one.
    """
    from pathlib import Path

    from .audio.reference import measure_bandwidth

    for voice in db.list_voices():
        if voice["qc"] or not voice["samples"]:
            continue
        sample = Path(voice["samples"][0])
        if not sample.exists():
            continue
        measured = measure_bandwidth(sample)
        if measured:
            db.set_voice_qc(voice["id"], measured)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    # Eager-load the TTS engine in the background. Ordering matters, not just
    # warm-up: torch must load its cuDNN DLLs before faster-whisper's
    # ctranslate2 gets a chance to expose an incompatible copy (crashes the
    # process with "Could not load symbol cudnnGetLibConfig" otherwise).
    import threading

    from .engines import get_engine

    threading.Thread(target=lambda: get_engine().load(), daemon=True).start()
    threading.Thread(target=_backfill_voice_qc, daemon=True).start()
    _backfill_generation_names()  # cheap, no audio decoding

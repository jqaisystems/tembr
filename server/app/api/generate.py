import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db
from ..audio.chunking import synthesize_chunked
from ..audio.post import post_process
from ..config import OUTPUT_DIR
from ..engines import engine_for_language, ensure_active

router = APIRouter(tags=["generate"])

MAX_TEXT = 8000  # long-form supported via chunking
NAME_WORDS = 6
NAME_MAX = 48


def name_from_text(text: str) -> str:
    """A short handle taken from the clip's own opening words.

    Every generation gets one so the history is scannable and downloads are not
    named after a 12-character id. The user can rename it afterwards.
    """
    words = re.sub(r"\s+", " ", text).strip().split(" ")[:NAME_WORDS]
    name = re.sub(r"[^\w\s'-]", "", " ".join(words)).strip()
    return (name[:NAME_MAX].rstrip() or "Untitled")


def unique_name(base: str) -> str:
    """`base`, or `base 02` onwards when that text has been generated before.

    Re-rolling the same line is the normal way to work here, so without this
    every take shares one name and they collide in the downloads folder.
    """
    taken = {n for n in db.generation_names_like(base)}
    if base not in taken:
        return base
    n = 2
    while f"{base} {n:02d}" in taken:
        n += 1
    return f"{base} {n:02d}"


def safe_filename(name: str, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return cleaned or fallback


class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT)
    voice_id: str | None = None  # None → engine default voice
    language: str = "en"
    engine: str | None = None  # None → auto-route by language (pt → qwen3tts)
    format: str = Field("wav", pattern="^(wav|mp3)$")
    normalize: bool = False  # EBU R128 loudness normalization via ffmpeg
    project: str = Field("", max_length=120)
    name: str = Field("", max_length=120)  # blank → derived from the text
    cfg_weight: float | None = Field(None, ge=0.0, le=1.0)
    exaggeration: float | None = Field(None, ge=0.0, le=2.0)
    # Each chunk is a separate pass and the joins are audible. Raise this to
    # keep a short piece in one breath (narration), leave it for long reads.
    max_chunk_chars: int | None = Field(None, ge=80, le=1200)


class GenerationUpdate(BaseModel):
    name: str | None = None
    favorite: bool | None = None


@router.post("/generate")
def generate(req: GenerateRequest):
    voice = None
    if req.voice_id:
        voice = db.get_voice(req.voice_id)
        if not voice:
            raise HTTPException(404, f"Voice '{req.voice_id}' not found.")

    # A cloned voice renders on the engine it was cloned with; an explicit
    # req.engine still overrides. Without a voice, route by language.
    engine_name = req.engine or (voice["engine"] if voice else engine_for_language(req.language))
    # qwen3tts is clone-only; the default voice always renders on chatterbox
    if not req.voice_id and engine_name == "qwen3tts":
        engine_name = "chatterbox"
    engine = ensure_active(engine_name)

    profile = None
    if voice:
        try:
            # voice_refs leads with the curated ten-second window when one
            # exists; the engines condition on refs[0].
            profile = engine.clone([Path(p) for p in db.voice_refs(voice)])
        except ValueError as e:
            raise HTTPException(400, str(e))

    gen_id = db.new_id()
    out_path = OUTPUT_DIR / f"{gen_id}.wav"
    t0 = time.time()
    try:
        chunk_opts = ({"max_chunk_chars": req.max_chunk_chars}
                      if req.max_chunk_chars else {})
        duration_s = synthesize_chunked(
            engine,
            profile,
            req.text,
            req.language,
            out_path,
            options={"cfg_weight": req.cfg_weight, "exaggeration": req.exaggeration},
            **chunk_opts,
        )
        final_path = post_process(out_path, req.format, req.normalize)
    except ValueError as e:
        raise HTTPException(400, str(e))
    elapsed = time.time() - t0

    gen = db.insert_generation(
        req.voice_id, engine_name, req.language, req.text, final_path, duration_s, elapsed,
        gid=gen_id, project=req.project.strip(),
        name=req.name.strip() or unique_name(name_from_text(req.text)),
    )
    gen["audio_url"] = f"/generations/{gen['id']}/audio"
    return gen


@router.get("/generations")
def generations(limit: int = 50, project: str | None = None):
    return db.list_generations(limit, project)


@router.get("/generations/projects")
def generation_projects():
    return db.list_generation_projects()


@router.patch("/generations/{gen_id}")
def patch_generation(gen_id: str, body: GenerationUpdate):
    if not db.get_generation(gen_id):
        raise HTTPException(404, "Generation not found.")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in fields:
        fields["name"] = fields["name"].strip()[:120]
        if not fields["name"]:
            raise HTTPException(400, "Name cannot be empty.")
    if "favorite" in fields:
        fields["favorite"] = int(fields["favorite"])
    if fields:  # an empty dict would render "UPDATE generations SET  WHERE id=?"
        db.update_generation(gen_id, **fields)
    return db.get_generation(gen_id)


@router.delete("/generations/{gen_id}")
def delete_generation(gen_id: str):
    """Permanent: removes the database entry AND the audio file on disk."""
    gen = db.get_generation(gen_id)
    if not gen:
        raise HTTPException(404, "Generation not found.")
    db.delete_generation(gen_id)
    Path(gen["output_path"]).unlink(missing_ok=True)
    return {"deleted": gen_id}


@router.get("/generations/{gen_id}/audio")
def generation_audio(gen_id: str):
    gen = db.get_generation(gen_id)
    if not gen or not Path(gen["output_path"]).exists():
        raise HTTPException(404, "Generation not found.")
    path = Path(gen["output_path"])
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    # The studio is served cross-origin from this API, so the browser ignores
    # the client's download="..." attribute and uses Content-Disposition. This
    # is what actually names the file on disk.
    stem = safe_filename(gen.get("name") or "", path.stem)
    return FileResponse(str(path), media_type=media, filename=f"{stem}{path.suffix}")

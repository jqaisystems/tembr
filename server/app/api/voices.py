import io
import json
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import db
from ..audio.reference import (
    CLEAN_CHAIN,
    clean_reference,
    cleanup_report,
    cut_window,
    measure_bandwidth,
    readable_by_engines,
    select_window,
    to_reference_wav,
)
from ..config import VOICES_DIR
from ..engines import DEFAULT_ENGINE, get_engine

router = APIRouter(prefix="/voices", tags=["voices"])

# What the engines' own reader (soundfile, via torchaudio) can open directly.
# Deliberately excludes .m4a and .webm: they used to be accepted here and then
# failed deep inside clone() with a LibsndfileError. Anything outside this set
# is transcoded to wav on the way in, so the studio takes almost any file.
NATIVE_EXTENSIONS = {".wav", ".flac", ".ogg", ".opus", ".mp3", ".aiff", ".aif", ".au", ".w64"}

MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".opus": "audio/ogg",
    ".webm": "audio/webm",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}


class VoiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    collection: str | None = None
    favorite: bool | None = None


def _land_sample(data: bytes, voice_dir: Path, index: int, filename: str) -> Path:
    """Land a sample in a format the engines can actually read.

    ffmpeg understands far more containers than they do, so anything it can
    decode becomes a usable reference. A file the engines can already read is
    kept as it is, which avoids a needless re-encode, but that is decided by
    opening it rather than by trusting its extension.
    """
    raw_ext = Path(filename or "sample.wav").suffix.lower()
    if raw_ext in NATIVE_EXTENSIONS:
        native = voice_dir / f"sample_{index}{raw_ext}"
        native.write_bytes(data)
        if readable_by_engines(native):
            return native
        native.unlink(missing_ok=True)  # mislabelled: fall through to ffmpeg

    incoming = voice_dir / f"incoming_{index}{raw_ext or '.bin'}"
    incoming.write_bytes(data)
    try:
        return to_reference_wav(incoming, voice_dir / f"sample_{index}.wav")
    finally:
        incoming.unlink(missing_ok=True)


async def _store_sample(upload: UploadFile, voice_dir: Path, index: int) -> Path:
    return _land_sample(await upload.read(), voice_dir, index, upload.filename or "")


def _discard(saved: list[str], voice_dir: Path) -> None:
    """Undo a failed ingest so no orphan files or directories are left."""
    for p in saved:
        Path(p).unlink(missing_ok=True)
    for leftover in voice_dir.glob("incoming_*"):
        leftover.unlink(missing_ok=True)
    if voice_dir.exists() and not any(voice_dir.iterdir()):
        voice_dir.rmdir()


def _curate_window(sample: Path, voice_dir: Path) -> dict | None:
    """Find and cut the conditioning window for a fresh reference.

    The engine hears mostly the first ten seconds of whatever file leads, so
    every new voice conditions on its strongest ten seconds instead of the
    start of the read, which is usually the stiffest part. The full recording
    stays untouched beside it for playback, QC and future fine-tuning. Never
    fatal: a voice without a window simply conditions on the full take, which
    is exactly the old behaviour.
    """
    try:
        found = select_window(sample)
        if not found:
            return None
        dest = voice_dir / "window_0.wav"
        cut_window(sample, dest, found["start_s"])
        return {**found, "path": str(dest)}
    except Exception:
        return None


class CleanupRequest(BaseModel):
    # "derive" keeps the original and adds a cleaned twin, which is the only way
    # to A/B them; "replace" swaps the samples in place and can be reverted.
    mode: str = "derive"
    chain: str = CLEAN_CHAIN


@router.post("")
async def create_voice(
    name: str = Form(...),
    description: str = Form(""),
    language: str = Form("en"),
    engine: str = Form(DEFAULT_ENGINE),
    consent: bool = Form(...),
    collection: str = Form(""),
    source: str = Form(""),
    samples: list[UploadFile] = File(...),
):
    if not consent:
        raise HTTPException(400, "Consent is required to create a voice profile.")

    voice_id = db.new_id()
    voice_dir = VOICES_DIR / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    try:
        for i, up in enumerate(samples):
            saved.append(str(await _store_sample(up, voice_dir, i)))
        profile = get_engine(engine).clone([Path(p) for p in saved])
    except ValueError as e:
        _discard(saved, voice_dir)
        raise HTTPException(400, str(e))
    except Exception as e:
        # torchaudio raises RuntimeError, not ValueError, for a file it cannot
        # decode. Left unhandled it 500s and strands files on disk.
        _discard(saved, voice_dir)
        raise HTTPException(400, f"Could not read that audio: {e}")

    # Measured here rather than trusting the client, so imports get a quality
    # reading too. One FFT pass, no whisper.
    voice = db.insert_voice(
        name, description, language, engine, saved, consent, vid=voice_id,
        collection=collection.strip()[:120], source=source.strip()[:60],
        qc=measure_bandwidth(Path(saved[0])),
        window=_curate_window(Path(saved[0]), voice_dir),
    )
    voice["profile"] = profile
    return voice


@router.get("")
def get_voices():
    return db.list_voices()


# Must stay above /{voice_id} or FastAPI matches the path param first and this
# 404s as a missing voice.
@router.get("/collections")
def voice_collections():
    return db.list_voice_collections()


@router.get("/{voice_id}")
def get_voice(voice_id: str):
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    return voice


@router.patch("/{voice_id}")
def patch_voice(voice_id: str, body: VoiceUpdate):
    if not db.get_voice(voice_id):
        raise HTTPException(404, "Voice not found.")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in fields and not fields["name"].strip():
        raise HTTPException(400, "Name cannot be empty.")
    if "collection" in fields:
        fields["collection"] = fields["collection"].strip()[:120]
    if "favorite" in fields:
        fields["favorite"] = int(fields["favorite"])
    if fields:  # an empty dict would render "UPDATE voices SET  WHERE id=?"
        db.update_voice(voice_id, **fields)
    return db.get_voice(voice_id)


@router.get("/{voice_id}/audio")
def voice_audio(voice_id: str):
    """The voice's reference recording, for playback in the studio."""
    voice = db.get_voice(voice_id)
    if not voice or not voice["samples"]:
        raise HTTPException(404, "Voice not found.")
    path = Path(voice["samples"][0])
    if not path.exists():
        raise HTTPException(404, "Sample file is missing on disk.")
    return FileResponse(
        str(path),
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
    )


@router.get("/{voice_id}/export")
def export_voice(voice_id: str):
    """Portable .voice zip: metadata + reference samples."""
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # Anything missing from this tuple is silently lost on a round trip.
        # "window" is deliberately excluded: import recomputes it from the
        # samples, so older exports gain the feature and paths never go stale.
        meta = {k: voice[k] for k in (
            "name", "description", "language", "engine", "consent",
            "collection", "source", "qc",
        )}
        z.writestr("voice.json", json.dumps(meta, ensure_ascii=False, indent=2))
        for p in voice["samples"]:
            path = Path(p)
            if path.exists():
                z.write(path, f"samples/{path.name}")
    buf.seek(0)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in voice["name"]).strip()
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name or voice_id}.voice"'},
    )


@router.post("/import")
async def import_voice(file: UploadFile = File(...), consent: bool = Form(...)):
    if not consent:
        raise HTTPException(400, "Consent is required to import a voice profile.")
    try:
        z = zipfile.ZipFile(io.BytesIO(await file.read()))
        meta = json.loads(z.read("voice.json"))
        sample_names = [n for n in z.namelist() if n.startswith("samples/") and not n.endswith("/")]
        if not sample_names:
            raise KeyError("samples")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        raise HTTPException(400, "Not a valid .voice file.")

    voice_id = db.new_id()
    voice_dir = VOICES_DIR / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    engine = meta.get("engine", DEFAULT_ENGINE)
    try:
        for i, name in enumerate(sample_names):
            # Transcode rather than skip: a .voice built elsewhere may hold
            # formats this machine's reader cannot open.
            saved.append(str(_land_sample(z.read(name), voice_dir, i, Path(name).name)))
        if not saved:
            raise ValueError("The .voice file contains no audio samples.")
        get_engine(engine).clone([Path(p) for p in saved])
    except ValueError as e:
        _discard(saved, voice_dir)
        raise HTTPException(400, str(e))
    except Exception as e:
        _discard(saved, voice_dir)
        raise HTTPException(400, f"Could not read that audio: {e}")

    return db.insert_voice(
        str(meta.get("name", "Imported voice")),
        str(meta.get("description", "")),
        str(meta.get("language", "en")),
        engine,
        saved,
        True,
        vid=voice_id,
        collection=str(meta.get("collection", ""))[:120],
        source=str(meta.get("source", ""))[:60],
        qc=measure_bandwidth(Path(saved[0])),
        window=_curate_window(Path(saved[0]), voice_dir),
    )


@router.post("/{voice_id}/cleanup")
def cleanup_voice(voice_id: str, body: CleanupRequest):
    """Denoise a voice's reference.

    Never automatic and never silent: a cleaned reference reads noticeably
    faster than the original, so both versions have to stay reachable. "derive"
    builds a twin and leaves the original alone; "replace" swaps in place and
    keeps the originals for revert.
    """
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    if body.mode not in ("derive", "replace"):
        raise HTTPException(400, "mode must be 'derive' or 'replace'.")
    sources = [Path(p) for p in voice["samples"] if Path(p).exists()]
    if not sources:
        raise HTTPException(400, "This voice has no sample files on disk.")

    before = measure_bandwidth(sources[0])
    try:
        if body.mode == "derive":
            new_id = db.new_id()
            new_dir = VOICES_DIR / new_id
            new_dir.mkdir(parents=True, exist_ok=True)
            cleaned = [
                str(clean_reference(src, new_dir / f"sample_{i}.wav", body.chain))
                for i, src in enumerate(sources)
            ]
        else:
            # Beside each original: two live voices keep their samples in another
            # voice's folder, so never assume VOICES_DIR/{voice_id}.
            cleaned = [
                str(clean_reference(src, src.with_suffix(".clean.wav"), body.chain))
                for src in sources
            ]
    except ValueError as e:
        raise HTTPException(400, str(e))

    after = measure_bandwidth(Path(cleaned[0]))
    report = cleanup_report(before, after, body.chain)

    if body.mode == "derive":
        taken = {v["name"] for v in db.list_voices()}
        base = f"{voice['name']} clean"
        name, n = base, 2
        while name in taken:
            name, n = f"{base} {n}", n + 1
        return db.insert_voice(
            name, voice["description"], voice["language"], voice["engine"],
            cleaned, voice["consent"], vid=new_id,
            collection=voice["collection"], source=voice["source"], qc=after,
            cleanup={**report, "applied": True, "mode": "derive", "from": voice_id},
        )

    db.update_voice(voice_id, samples=json.dumps(cleaned))
    db.set_voice_cleanup(voice_id, {
        **report, "applied": True, "mode": "replace",
        "original": [str(p) for p in sources],
    })
    db.set_voice_qc(voice_id, after)
    # A voice that conditions on a curated window must re-curate from the
    # cleaned audio; a windowless voice stays windowless (its sound is trusted
    # as it is, and nothing here changes that decision).
    if voice.get("window"):
        db.set_voice_window(
            voice_id, _curate_window(Path(cleaned[0]), VOICES_DIR / voice_id))
    return db.get_voice(voice_id)


@router.post("/{voice_id}/cleanup/revert")
def revert_cleanup(voice_id: str):
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    info = voice.get("cleanup") or {}
    originals = [p for p in info.get("original", []) if Path(p).exists()]
    if not originals:
        raise HTTPException(400, "This voice has no original recording to restore.")
    for p in voice["samples"]:
        if p not in originals:
            Path(p).unlink(missing_ok=True)
    db.update_voice(voice_id, samples=json.dumps(originals))
    db.set_voice_cleanup(voice_id, None)
    db.set_voice_qc(voice_id, measure_bandwidth(Path(originals[0])))
    if voice.get("window"):
        db.set_voice_window(
            voice_id, _curate_window(Path(originals[0]), VOICES_DIR / voice_id))
    return db.get_voice(voice_id)


@router.post("/{voice_id}/window")
def window_voice(voice_id: str):
    """Derive a twin that conditions on its best ten seconds.

    The engine hears mostly the first ten seconds of a reference, so this
    finds the strongest stretch of the take and leads with it. Derive-only,
    like cleanup's derive mode: the original voice never changes, so the two
    can be compared by ear before either is trusted.
    """
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    sources = [Path(p) for p in voice["samples"] if Path(p).exists()]
    if not sources:
        raise HTTPException(400, "This voice has no sample files on disk.")

    new_id = db.new_id()
    new_dir = VOICES_DIR / new_id
    new_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for i, src in enumerate(sources):
        dest = new_dir / f"sample_{i}{src.suffix}"
        shutil.copy(src, dest)
        copied.append(str(dest))
    window = _curate_window(Path(copied[0]), new_dir)
    if not window:
        _discard(copied, new_dir)
        raise HTTPException(
            400,
            "No window to pick: the take is already about ten seconds or "
            "shorter, so the engine hears all of it as it is.",
        )
    window["from"] = voice_id

    taken = {v["name"] for v in db.list_voices()}
    base = f"{voice['name']} tuned"
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return db.insert_voice(
        name, voice["description"], voice["language"], voice["engine"],
        copied, voice["consent"], vid=new_id,
        collection=voice["collection"], source=voice["source"],
        qc=measure_bandwidth(Path(copied[0])), window=window,
    )


@router.delete("/{voice_id}")
def remove_voice(voice_id: str):
    voice = db.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    db.delete_voice(voice_id)
    # Includes the pre-cleanup originals, which a "replace" leaves on disk
    # beside the cleaned files and nothing else would ever remove, plus the
    # curated conditioning window.
    stale = set(voice["samples"]) | set((voice.get("cleanup") or {}).get("original", []))
    window_path = (voice.get("window") or {}).get("path")
    if window_path:
        stale.add(window_path)
    for p in stale:
        Path(p).unlink(missing_ok=True)
    # Only this voice's own directory: some voices keep samples in another's.
    voice_dir = VOICES_DIR / voice_id
    if voice_dir.exists() and not any(voice_dir.iterdir()):
        voice_dir.rmdir()
    return {"deleted": voice_id}

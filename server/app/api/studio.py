"""Phase 2 endpoints: recording script library + whisper QC transcription."""
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from ..audio.reference import (
    CLEAN_CHAIN,
    GOOD_PRESENCE_DB,
    GOOD_REACH_HZ,
    GOOD_SAMPLE_RATE,
    GOOD_SNR_DB,
    POOR_PRESENCE_DB,
    POOR_REACH_HZ,
    clean_reference,
    cleanup_report,
    measure_bandwidth,
    thresholds,
    to_reference_wav,
)
from ..config import TMP_DIR
from ..scripts_data import list_scripts, script_guide

router = APIRouter(tags=["studio"])

_whisper = None

MIN_GOOD_SECONDS = 10.0


def _get_whisper():
    global _whisper
    if _whisper is None:
        import torch  # noqa: F401 — torch's cuDNN DLLs must be loaded before ctranslate2's

        from faster_whisper import WhisperModel

        # small + CPU int8: QC runs occasionally and must not evict the TTS
        # model from VRAM.
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper


@router.get("/scripts")
def scripts(language: str | None = None):
    return list_scripts(language)


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    tmp_path = TMP_DIR / f"qc_{uuid.uuid4().hex[:8]}{suffix}"
    tmp_path.write_bytes(await file.read())
    try:
        band = measure_bandwidth(tmp_path)
        model = _get_whisper()
        segments, info = model.transcribe(str(tmp_path), vad_filter=True)
        segs = list(segments)
    except Exception as e:
        raise HTTPException(400, f"Could not transcribe audio: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    text = " ".join(s.text.strip() for s in segs)
    speech_s = sum(s.end - s.start for s in segs)

    warnings = []
    if info.duration < MIN_GOOD_SECONDS:
        warnings.append(
            f"Recording is {info.duration:.1f}s. Aim for at least {MIN_GOOD_SECONDS:.0f}s of speech."
        )
    if info.duration > 0 and speech_s / info.duration < 0.5:
        warnings.append("More than half the recording is silence. Trim it, or re-record closer to the mic.")
    if segs and sum(s.no_speech_prob for s in segs) / len(segs) > 0.5:
        warnings.append("Speech is hard to detect. Check for background noise or low volume.")
    if not segs:
        warnings.append("No speech detected in this recording.")
    if band:
        if band["sample_rate"] < GOOD_SAMPLE_RATE:
            warnings.append(
                f"Recorded at {band['sample_rate'] / 1000:.0f} kHz, which caps the "
                f"voice at {band['sample_rate'] / 2000:.0f} kHz. The engines "
                "generate at 24 kHz. This is usually a Bluetooth headset in call "
                "mode or a virtual voice chat microphone. Use a wired or USB mic, "
                "or your phone's own voice recorder app."
            )
        elif band["reach_hz"] < POOR_REACH_HZ:
            warnings.append(
                f"The voice stops at {band['reach_hz'] / 1000:.1f} kHz even though "
                "the file allows more, so something in the chain is band-limiting "
                "it. Avoid Bluetooth microphones and messaging apps, which re-encode "
                "to narrowband."
            )
        if band["presence_db"] < POOR_PRESENCE_DB:
            warnings.append(
                "The recording is dull in the 4 to 8 kHz range, where consonants "
                "live. Move closer to the microphone, a hand's width away, and aim "
                "it at your mouth slightly off to one side."
            )
        elif band["presence_db"] < GOOD_PRESENCE_DB:
            warnings.append(
                "A little dull up high. Moving closer to the microphone will give "
                "the clone crisper consonants."
            )
        if band["snr_db"] < GOOD_SNR_DB:
            warnings.append(
                f"Only {band['snr_db']:.0f} dB between your voice and the room. The "
                "clone copies room tone as well as voice, so record somewhere "
                "quieter or closer to the mic. Aim for 55 dB or more."
            )

    return {
        "text": text,
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "duration_s": round(info.duration, 1),
        "speech_s": round(speech_s, 1),
        "sample_rate": band["sample_rate"] if band else None,
        "reach_hz": round(band["reach_hz"]) if band else None,
        "presence_db": round(band["presence_db"], 1) if band else None,
        "snr_db": round(band["snr_db"], 1) if band else None,
        "thresholds": thresholds(),
        "warnings": warnings,
    }


@router.get("/scripts/guide")
def scripts_guide(language: str | None = None):
    return script_guide(language)


# ---------------------------------------------------------------- cleanup
# A take in the record flow is not a voice yet, so trying a cleanup has to work
# on a loose file. The result parks in TMP_DIR until the user picks a version.

CLEAN_PREFIX = "clean_"
CLEAN_TTL_S = 2 * 60 * 60
_TOKEN_RE = re.compile(r"^[0-9a-f]{8,32}$")


def _sweep_cleanups() -> None:
    cutoff = time.time() - CLEAN_TTL_S
    for old in TMP_DIR.glob(f"{CLEAN_PREFIX}*.wav"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink(missing_ok=True)
        except OSError:
            pass


def _clean_path(token: str) -> Path:
    if not _TOKEN_RE.match(token):
        raise HTTPException(404, "Unknown cleanup.")
    path = (TMP_DIR / f"{CLEAN_PREFIX}{token}.wav").resolve()
    if path.parent != TMP_DIR.resolve() or not path.exists():
        raise HTTPException(404, "Unknown cleanup.")
    return path


@router.post("/cleanup")
async def cleanup(file: UploadFile = File(...), chain: str = Form(CLEAN_CHAIN)):
    """Denoise a take that has not been saved as a voice yet, and report the cost."""
    _sweep_cleanups()
    token = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    src = TMP_DIR / f"{CLEAN_PREFIX}src_{token}{suffix}"
    dest = TMP_DIR / f"{CLEAN_PREFIX}{token}.wav"
    src.write_bytes(await file.read())
    try:
        before = measure_bandwidth(src)
        clean_reference(src, dest, chain)
        after = measure_bandwidth(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    finally:
        src.unlink(missing_ok=True)
    return {"id": token, "audio_url": f"/cleanup/{token}/audio", **cleanup_report(before, after, chain)}


@router.get("/cleanup/{token}/audio")
def cleanup_audio(token: str):
    return FileResponse(str(_clean_path(token)), media_type="audio/wav")


@router.post("/convert")
async def convert(file: UploadFile = File(...)):
    """Turn any container ffmpeg reads into a wav the browser can play.

    The studio decodes uploads in the browser so it can draw the waveform, but
    Chrome cannot decode everything a phone or recorder produces. This is the
    fallback for those, so people are not turned away for having an .amr or a
    .wma.
    """
    token = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "audio").suffix.lower()
    src = TMP_DIR / f"conv_{token}{suffix or '.bin'}"
    dest = TMP_DIR / f"conv_{token}.wav"
    src.write_bytes(await file.read())
    try:
        to_reference_wav(src, dest)
        return Response(content=dest.read_bytes(), media_type="audio/wav")
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        src.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)

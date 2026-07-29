"""Post-processing via ffmpeg: MP3 export and loudness normalization."""
import shutil
import subprocess
from pathlib import Path

# EBU R128 target suited to voice notes / podcast distribution.
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def post_process(wav_path: Path, fmt: str, normalize: bool) -> Path:
    """Convert/normalize wav_path. Returns the final audio path.

    fmt "wav" without normalization is a no-op. MP3 output replaces the wav.
    """
    if fmt == "wav" and not normalize:
        return wav_path
    if not ffmpeg_available():
        raise ValueError("ffmpeg is not installed. Only WAV without normalization is available.")

    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path)]
    if normalize:
        args += ["-af", LOUDNORM]
    if fmt == "mp3":
        out = wav_path.with_suffix(".mp3")
        args += ["-codec:a", "libmp3lame", "-b:a", "192k", str(out)]
    else:
        out = wav_path.with_name(wav_path.stem + "_norm.wav")
        args += [str(out)]

    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise ValueError(f"ffmpeg failed: {result.stderr.strip()[:300]}")

    wav_path.unlink(missing_ok=True)
    if fmt == "wav":
        final = wav_path
        out.rename(final)
        return final
    return out

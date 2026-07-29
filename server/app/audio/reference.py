"""Measuring and cleaning reference recordings.

A zero-shot clone is only ever as good as the take it is built from: the model
copies the microphone and the room along with the voice. These helpers answer
the two questions that decide a reference, "is this take good enough" and "can
it be rescued", using measurements rather than guesswork.
"""
import subprocess
from pathlib import Path

from .post import ffmpeg_available

# The engines synthesize at 24 kHz. A reference has to carry real detail up
# high, or the model invents that band from its own prior, which is heard as
# noise or a drifting accent.
#
# Deliberately NOT measured as cumulative energy rolloff: voiced speech puts
# almost all its energy under 1 kHz however good the microphone is, so that
# number stays low for a perfectly good recording. What matters is how far up
# real detail survives above the room tone, and how strong the 4-8 kHz
# consonant band is relative to the body of the voice.
GOOD_REACH_HZ = 9000.0    # below this the device is band-limiting the voice
POOR_REACH_HZ = 7000.0    # a hard wall here means a narrowband device
GOOD_PRESENCE_DB = -55.0  # 4-8 kHz level relative to the loudest band
POOR_PRESENCE_DB = -62.0
GOOD_SNR_DB = 55.0
GOOD_SAMPLE_RATE = 24000

# Measured on a real 48 kHz phone reference: noise floor -60.4 to -65.4 dB and
# voice-above-room 47.4 to 52.0, with the 15.8 kHz reach untouched. No -ar and
# no loudnorm on purpose. Preserving the sample rate is why the bandwidth
# survived, and re-levelling would be a second uncontrolled change to a take
# whose delivery this already alters.
CLEAN_CHAIN = "highpass=f=70,afftdn=nr=14:nf=-48:tn=1"

# Below this the cleanup is not worth the delivery it costs.
WORTHWHILE_GAIN_DB = 2.0


def thresholds() -> dict:
    """The numbers the UI gates on, so the client cannot drift from the server."""
    return {
        "good_reach_hz": GOOD_REACH_HZ,
        "poor_reach_hz": POOR_REACH_HZ,
        "good_presence_db": GOOD_PRESENCE_DB,
        "poor_presence_db": POOR_PRESENCE_DB,
        "good_snr_db": GOOD_SNR_DB,
        "good_sample_rate": GOOD_SAMPLE_RATE,
    }


def measure_bandwidth(path: Path) -> dict | None:
    """How far the microphone reaches, how bright it is, and how quiet."""
    try:
        import numpy as np
        import soundfile as sf

        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        return None
    x = x.mean(axis=1)
    win = 2048
    if len(x) < win * 8:
        return None
    n = len(x) // win
    frames = x[: n * win].reshape(n, win)
    rms = np.sqrt(np.maximum((frames ** 2).mean(axis=1), 1e-12))
    db = 20 * np.log10(rms)
    speech = frames[db >= np.percentile(db, 75)]
    room = frames[db <= np.percentile(db, 10)]
    if len(speech) == 0:
        return None

    window = np.hanning(win)
    freqs = np.fft.rfftfreq(win, 1 / sr)

    def spectrum(block):
        return np.abs(np.fft.rfft(block * window, axis=1)).mean(axis=0)

    voice = spectrum(speech)
    peak = voice.max()
    if peak <= 0:
        return None
    voice_db = 20 * np.log10(np.maximum(voice, 1e-12) / peak)
    room_db = (20 * np.log10(np.maximum(spectrum(room), 1e-12) / peak)
               if len(room) else np.full_like(voice_db, -200.0))

    # reach: the highest frequency where speech still stands clear of the room
    clear = np.where((voice_db > room_db + 6) & (freqs > 500))[0]
    reach = float(freqs[clear[-1]]) if len(clear) else 0.0

    band = (freqs >= 4000) & (freqs <= 8000)
    presence = float(voice_db[band].mean()) if band.any() else -120.0
    snr = float(np.percentile(db, 95) - np.percentile(db, 5))
    return {
        "sample_rate": int(sr),
        "reach_hz": reach,
        "presence_db": presence,
        "snr_db": snr,
        "duration_s": round(len(x) / sr, 2),
    }


def readable_by_engines(path: Path) -> bool:
    """Can the engines' own reader open this file?

    Extensions lie. A phone recorder happily writes an MP4 container named
    .mp3, which passes any extension check and then fails deep inside cloning.
    Asking the actual reader is the only honest test.
    """
    try:
        import soundfile as sf

        sf.info(str(path))
        return True
    except Exception:
        return False


def to_reference_wav(src: Path, dest: Path) -> Path:
    """Normalise any container ffmpeg can read into a wav the engines can.

    The engines validate references with torchaudio, whose only backend here is
    soundfile, and soundfile cannot read MP4/AAC (.m4a), WebM, WMA, AMR or 3GP.
    Storing an upload under its original extension therefore fails deep inside
    clone() with a LibsndfileError, which is a RuntimeError and escapes the
    ValueError handling. Transcoding on the way in removes the whole class of
    failure and means people can bring whatever their phone or recorder made.

    Mono because every engine mixes down anyway. No -ar: the source sample rate
    carries the bandwidth that decides clone quality.
    """
    if not ffmpeg_available():
        raise ValueError(
            "ffmpeg is not installed, so this audio format cannot be converted. "
            "Install ffmpeg, or upload a wav, flac, ogg or mp3 file."
        )
    args = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vn", "-ac", "1", "-c:a", "pcm_s16le", str(dest),
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not dest.exists():
        raise ValueError(
            "Could not read any audio from that file. "
            f"ffmpeg said: {result.stderr.strip()[:200]}"
        )
    return dest


def clean_reference(src: Path, dest: Path, chain: str = CLEAN_CHAIN) -> Path:
    """Run the denoise chain, keeping the sample rate and the level as they are."""
    if not ffmpeg_available():
        raise ValueError("ffmpeg is not installed, so cleanup is unavailable.")
    args = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-af", chain, "-c:a", "pcm_s16le", str(dest),
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise ValueError(f"ffmpeg failed: {result.stderr.strip()[:300]}")
    return dest


WINDOW_S = 10.0        # chatterbox's decoder hears exactly this much
MIN_SCAN_S = 12.0      # under this the whole file already is the window


def select_window(path: Path, length_s: float = WINDOW_S) -> dict | None:
    """Find the strongest ~10 second stretch of a reference recording.

    The engine conditions its decoder on the FIRST ten seconds of whatever
    file it is handed and its token prompt on the first six; the rest of the
    recording only feeds a weak averaged embedding. So whichever ten seconds
    lead the file decide the accent and the character of the clone. This scan
    finds the stretch where the voice is most present: windows snapped to
    speech onsets, scored by voiced density times pitch liveliness, because a
    monotone window under-specifies the accent and the model's own prior
    leaks in.

    Returns {"start_s", "end_s", "score", "default_score"} or None when the
    file is short enough to be its own window (or nothing is scoreable).
    """
    try:
        import librosa
        import numpy as np
        import soundfile as sf

        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        return None
    x = x.mean(axis=1)
    dur = len(x) / sr
    if dur <= MIN_SCAN_S:
        return None

    # energy frames -> speech onsets (a window must not start mid-word)
    hop = 0.02
    win = int(hop * sr)
    n = len(x) // win
    rms = np.sqrt(np.maximum((x[: n * win].reshape(n, win) ** 2).mean(axis=1), 1e-12))
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 5)
    speaking = db > floor + 20

    onsets = [0.0]
    quiet = 0
    for i in range(1, n):
        if not speaking[i]:
            quiet += 1
        else:
            if quiet * hop >= 0.35:
                onsets.append(i * hop)
            quiet = 0

    # pitch once over the whole file at 16 kHz, windows aggregate from it
    try:
        y16 = librosa.resample(x, orig_sr=sr, target_sr=16000)
        f0, vflag, _ = librosa.pyin(y16, fmin=60, fmax=320, sr=16000,
                                    frame_length=1024, hop_length=256)
    except Exception:
        return None
    t_f0 = librosa.frames_to_time(np.arange(len(f0)), sr=16000, hop_length=256)

    def score_at(start: float) -> float | None:
        m = (t_f0 >= start) & (t_f0 < start + length_s)
        v = vflag[m].astype(float)
        st = f0[m]
        st = st[~np.isnan(st)]
        if v.size == 0 or len(st) < 20:
            return None
        semis = 12 * np.log2(st / np.median(st))
        return float(np.nanmean(v)) * float(np.std(semis))

    best = None
    for start in onsets:
        if start + length_s > dur:
            break
        s = score_at(start)
        if s is not None and (best is None or s > best[0]):
            best = (s, start)
    if best is None:
        return None
    default = score_at(0.0) or 0.0
    return {
        "start_s": round(best[1], 2),
        "end_s": round(best[1] + length_s, 2),
        "score": round(best[0], 3),
        "default_score": round(default, 3),
    }


def cut_window(src: Path, dest: Path, start_s: float,
               length_s: float = WINDOW_S) -> Path:
    """Cut the conditioning window: tiny fades, sample rate untouched."""
    if not ffmpeg_available():
        raise ValueError("ffmpeg is not installed, so the window cannot be cut.")
    fade_out = max(0.0, length_s - 0.05)
    args = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{max(0.0, start_s - 0.05):.3f}", "-t", f"{length_s:.3f}",
        "-i", str(src),
        "-af", f"afade=t=in:d=0.03,afade=t=out:st={fade_out:.3f}:d=0.05",
        "-c:a", "pcm_s16le", str(dest),
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not dest.exists():
        raise ValueError(f"ffmpeg failed: {result.stderr.strip()[:300]}")
    return dest


def cleanup_report(before: dict | None, after: dict | None, chain: str) -> dict:
    """Whether a cleanup earned its keep, in the terms the UI explains it in."""
    gain = 0.0
    reach_kept = True
    if before and after:
        gain = round(after["snr_db"] - before["snr_db"], 1)
        # losing more than a tenth of the reach means the chain ate real detail
        reach_kept = after["reach_hz"] >= before["reach_hz"] * 0.9
    return {
        "chain": chain,
        "before": before,
        "after": after,
        "gain_db": gain,
        "reach_kept": reach_kept,
        "worthwhile": gain >= WORTHWHILE_GAIN_DB and reach_kept,
    }

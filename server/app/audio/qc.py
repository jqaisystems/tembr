"""Automatic per-note QC, run after every outreach render and re-render.

Two failure families the engines produce now and then:
  - long dead pauses in the middle of a note (ffmpeg silencedetect)
  - mangled endings: a repeated word or hallucinated trailing syllables
    (whisper transcript compared against the expected script)

Checks are tuned for precision over recall: a false "this note is broken"
teaches the user to ignore the flags. QC failures never block the note.
"""
import re
import subprocess
import time
from pathlib import Path

PAUSE_THRESHOLD_S = 1.0

_SIL_RE = re.compile(r"silence_duration:\s*([\d.]+)")


def _norm_words(text: str) -> list[str]:
    return [w for w in re.sub(r"[^\w\s']", " ", text.lower()).split() if w]


def _pause_warnings(path: Path) -> list[str]:
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", str(path),
                "-af", f"silencedetect=noise=-35dB:d={PAUSE_THRESHOLD_S}",
                "-f", "null", "-",
            ],
            capture_output=True,
            timeout=60,
        )
        pauses = [float(m) for m in _SIL_RE.findall(result.stderr.decode(errors="replace"))]
        if pauses:
            return [f"Dead pause of {max(pauses):.1f}s inside the note."]
    except Exception:
        pass
    return []


def _ending_warnings(path: Path, expected_text: str) -> list[str]:
    try:
        # Shares the CPU whisper singleton; torch is already loaded at startup,
        # so the cuDNN ordering trap does not apply here.
        from ..api.studio import _get_whisper

        segments, _info = _get_whisper().transcribe(str(path), vad_filter=True)
        heard = _norm_words(" ".join(s.text.strip() for s in segments))
        expected = _norm_words(expected_text)
        warnings = []

        # Repeated ending phrase ("about it ... about it"), the engines' most
        # common stutter. The copies are often separated by a connective or a
        # breath, so the final phrase is searched for anywhere in the stretch
        # just before it, not only immediately adjacent.
        for k in range(2, 11):
            if len(heard) < k + 2:
                break
            tail = heard[-k:]
            window = heard[max(0, len(heard) - 2 * k - 4) : -k]
            if any(window[i : i + k] == tail for i in range(len(window) - k + 1)):
                warnings.append("The ending repeats itself in the note.")
                break

        # Hallucinated trailing syllables: judged only when the script's real
        # ending is clearly found in the transcript (keeps precision high).
        # First occurrence, so a repeated ending also counts as extra audio.
        anchor = expected[-3:]
        if len(anchor) == 3 and len(heard) >= 3:
            end_pos = -1
            for i in range(len(heard) - len(anchor) + 1):
                if heard[i : i + len(anchor)] == anchor:
                    end_pos = i + len(anchor)
                    break
            if end_pos != -1 and len(heard) - end_pos >= 2:
                if not warnings:
                    warnings.append("Extra sounds after the ending of the script.")
        return warnings
    except Exception:
        return []


def qc_note(path: Path, expected_text: str) -> dict:
    warnings = _pause_warnings(path) + _ending_warnings(path, expected_text)
    return {"warnings": warnings, "checked_at": time.time()}

"""Long-text support: split text into sentence-boundary chunks each engine can
handle comfortably, synthesize per chunk, concatenate with natural pauses."""
import re
from pathlib import Path

# One chunk is one model pass, and every pass gets its own vocal energy, so
# each split is an audible seam where the voice changes character. Keep pieces
# whole as long as the engine stays coherent. Measured 2026-07-28: a 346-char
# narration split at 280 came back as two takes stitched together and was
# rejected for inconsistency; the same text in one pass at this limit was
# steady (brightness spread 53% -> 36%) and pronounced better.
MAX_CHUNK_CHARS = 600
PAUSE_SECONDS = 0.25

_SENTENCE_RE = re.compile(r"[^.!?…\n]+[.!?…]*\s*", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    sentences = [m.group(0).strip() for m in _SENTENCE_RE.finditer(text)]
    return [s for s in sentences if s]


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        # A single oversized sentence becomes its own chunk rather than being
        # cut mid-phrase — engines cope better with a long sentence than a
        # fragment that ends nowhere.
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def synthesize_chunked(engine, profile, text, language, out_path: Path, options=None,
                       max_chunk_chars: int = MAX_CHUNK_CHARS) -> float:
    """Synthesize text (chunking when long) to out_path. Returns duration.

    Every chunk is a separate pass through the model, so each one gets its own
    energy and the joins are audible as the voice shifting. Fine for a long
    read; wrong for something short that has to sound like one breath, such as
    video narration. Raise max_chunk_chars to keep a piece whole.
    """
    import numpy as np
    import soundfile as sf

    chunks = chunk_text(text, max_chunk_chars)
    if len(chunks) == 1:
        return engine.synthesize(profile, chunks[0], language, out_path, options=options)

    def voiced_rms(x):
        """Loudness of the speech itself, with the pauses gated out."""
        frame = max(int(sample_rate * 0.02), 1)
        m = len(x) // frame
        if m == 0:
            return 0.0
        levels = np.sqrt(np.maximum((x[: m * frame].reshape(m, frame) ** 2).mean(axis=1), 1e-12))
        voiced = levels[levels > levels.max() * 0.01]  # ~ -40 dB gate
        return float(voiced.mean()) if len(voiced) else 0.0

    pieces = []
    sample_rate = None
    anchor = None
    for i, chunk in enumerate(chunks):
        part_path = out_path.with_suffix(f".part{i}.wav")
        engine.synthesize(profile, chunk, language, part_path, options=options)
        data, sr = sf.read(str(part_path), dtype="float32")
        part_path.unlink(missing_ok=True)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sample_rate is None:
            sample_rate = sr
        elif sr != sample_rate:
            raise ValueError("Engine returned inconsistent sample rates across chunks.")
        # Each pass arrives at its own loudness, and the jump at the join is
        # the most audible part of the seam. Match every chunk to the first,
        # capped at ~6 dB so a broken take is not amplified into prominence.
        level = voiced_rms(data)
        if anchor is None:
            anchor = level
        elif level > 0 and anchor > 0:
            data = data * float(np.clip(anchor / level, 0.5, 2.0))
        pieces.append(data)

    pause = np.zeros(int(sample_rate * PAUSE_SECONDS), dtype="float32")
    joined = pieces[0]
    for piece in pieces[1:]:
        joined = np.concatenate([joined, pause, piece])
    sf.write(str(out_path), joined, sample_rate)
    return len(joined) / sample_rate

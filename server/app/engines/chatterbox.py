import time
from pathlib import Path

from .base import BaseEngine

# Chatterbox Multilingual language ids (subset shown in UI later)
CHATTERBOX_LANGUAGES = [
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
]

MIN_REFERENCE_SECONDS = 5.0


class ChatterboxEngine(BaseEngine):
    name = "chatterbox"
    languages = CHATTERBOX_LANGUAGES

    def __init__(self) -> None:
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.time()
        self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        print(f"[chatterbox] loaded on {device} in {time.time() - t0:.1f}s")

    def clone(self, reference_wavs: list[Path]) -> dict:
        import torchaudio

        if not reference_wavs:
            raise ValueError("At least one reference recording is required.")
        # Zero-shot: the profile is the (validated) reference audio itself.
        primary = reference_wavs[0]
        info = torchaudio.info(str(primary))
        seconds = info.num_frames / info.sample_rate
        if seconds < MIN_REFERENCE_SECONDS:
            raise ValueError(
                f"Reference audio is {seconds:.1f}s. It needs at least "
                f"{MIN_REFERENCE_SECONDS:.0f}s of clean speech."
            )
        return {"audio_prompt_path": str(primary), "reference_seconds": round(seconds, 1)}

    def synthesize(
        self,
        profile: dict | None,
        text: str,
        language: str,
        out_path: Path,
        options: dict | None = None,
    ) -> float:
        import torchaudio

        self.load()
        if language not in self.languages:
            raise ValueError(f"Language '{language}' not supported by chatterbox.")
        kwargs = {}
        if profile and profile.get("audio_prompt_path"):
            kwargs["audio_prompt_path"] = profile["audio_prompt_path"]
        # cfg_weight: how strongly the model follows its own language prior vs
        # the reference speaker. Lower keeps more of the reference accent
        # (e.g. pt-PT instead of the model's Brazilian-leaning "pt").
        for key in ("cfg_weight", "exaggeration", "temperature"):
            if options and options.get(key) is not None:
                kwargs[key] = float(options[key])
        wav = self._model.generate(text, language_id=language, **kwargs)
        # 16-bit PCM, not torchaudio's default 32-bit float: browsers refuse to
        # play float WAV in an <audio> element, so a wav generation would look
        # fine on disk and stay silent in the studio.
        torchaudio.save(
            str(out_path),
            wav.cpu().clamp(-1.0, 1.0),
            self._model.sr,
            encoding="PCM_S",
            bits_per_sample=16,
        )
        return wav.shape[-1] / self._model.sr

    def unload(self) -> None:
        if self._model is not None:
            import gc

            import torch

            self._model = None
            gc.collect()
            torch.cuda.empty_cache()
            print("[chatterbox] unloaded, VRAM released")

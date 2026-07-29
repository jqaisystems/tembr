"""Engine abstraction: every TTS engine implements this interface.

Zero-shot engines (Chatterbox, Qwen3-TTS) don't train anything in clone() —
they validate reference audio and return profile data that synthesize()
uses as the voice prompt.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class BaseEngine(ABC):
    name: str = "base"
    languages: list[str] = []

    @abstractmethod
    def load(self) -> None:
        """Load model weights onto the GPU. Called once, lazily."""

    @abstractmethod
    def clone(self, reference_wavs: list[Path]) -> dict:
        """Validate reference audio, return engine-specific profile data."""

    @abstractmethod
    def synthesize(
        self,
        profile: dict | None,
        text: str,
        language: str,
        out_path: Path,
        options: dict | None = None,
    ) -> float:
        """Generate speech to out_path (wav). profile=None → engine default voice.

        options: engine-specific tuning knobs (e.g. cfg_weight for chatterbox).
        Returns audio duration in seconds.
        """

    def unload(self) -> None:
        pass

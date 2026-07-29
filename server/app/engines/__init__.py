"""Engine registry — engines are constructed lazily so the API starts fast
and torch/model imports only happen on first use."""
from .base import BaseEngine

_instances: dict[str, BaseEngine] = {}

ENGINE_NAMES = ["chatterbox", "qwen3tts"]  # kokoro arrives in a later phase
DEFAULT_ENGINE = "chatterbox"

# Per-language engine preference, decided by ear in A/B tests: Qwen's
# Portuguese sounds European where Chatterbox's leans Brazilian, while in
# English Chatterbox held the reference accent better, so en routes there.
# Chatterbox is also the default-voice engine and covers the languages Qwen lacks.
LANGUAGE_ENGINE_OVERRIDES = {"pt": "qwen3tts"}


def engine_for_language(language: str) -> str:
    return LANGUAGE_ENGINE_OVERRIDES.get(language, DEFAULT_ENGINE)


def ensure_active(name: str) -> BaseEngine:
    """One heavyweight engine on the GPU at a time (12 GB card): unload every
    other engine before handing back the requested one."""
    engine = get_engine(name)
    for other_name, other in _instances.items():
        if other_name != name:
            other.unload()
    return engine


def get_engine(name: str = DEFAULT_ENGINE) -> BaseEngine:
    if name not in ENGINE_NAMES:
        raise ValueError(f"Unknown engine '{name}'. Available: {ENGINE_NAMES}")
    if name not in _instances:
        if name == "chatterbox":
            from .chatterbox import ChatterboxEngine

            _instances[name] = ChatterboxEngine()
        elif name == "qwen3tts":
            from .qwen3tts import Qwen3TTSEngine

            _instances[name] = Qwen3TTSEngine()
    return _instances[name]

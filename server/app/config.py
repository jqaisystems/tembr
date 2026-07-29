"""Central paths + environment setup.

Import this module FIRST (before torch/transformers/chatterbox) so that all
model caches land inside the project instead of the system drive.
"""
import os
from pathlib import Path

# the repository root
BASE_DIR = Path(__file__).resolve().parents[2]

MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
VOICES_DIR = DATA_DIR / "voices"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "studio.db"
TMP_DIR = BASE_DIR / ".cache" / "tmp"

# Keep every cache off C: — must happen before huggingface/torch imports.
os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("TORCH_HOME", str(MODELS_DIR / "torch"))
os.environ.setdefault("TMP", str(TMP_DIR))
os.environ.setdefault("TEMP", str(TMP_DIR))

for _d in (MODELS_DIR, VOICES_DIR, OUTPUT_DIR, TMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

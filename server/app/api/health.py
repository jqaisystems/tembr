import shutil

from fastapi import APIRouter

from ..config import BASE_DIR, MODELS_DIR
from ..engines import ENGINE_NAMES

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    info = {"status": "ok", "engines": ENGINE_NAMES, "base_dir": str(BASE_DIR)}

    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            free_b, total_b = torch.cuda.mem_get_info()
            info["gpu"] = {
                "name": torch.cuda.get_device_name(0),
                "vram_total_gb": round(total_b / 1e9, 1),
                "vram_free_gb": round(free_b / 1e9, 1),
            }
    except ImportError:
        info["torch"] = None

    usage = shutil.disk_usage(BASE_DIR)
    info["disk"] = {
        "drive": BASE_DIR.drive,
        "free_gb": round(usage.free / 1e9, 1),
        "models_gb": round(
            sum(f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file()) / 1e9, 2
        ),
    }
    return info

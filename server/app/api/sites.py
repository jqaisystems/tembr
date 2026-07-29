"""Local preview of built player page bundles.

Serves data/outreach/{job_id}/site/ so a batch's pages can be opened in the
browser exactly as they will look on a static host. Path traversal is blocked
by resolving against the site root.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import DATA_DIR

router = APIRouter(tags=["sites"])

OUTREACH_DIR = DATA_DIR / "outreach"


@router.get("/sites/{job_id}/{path:path}")
def site_file(job_id: str, path: str = ""):
    base = (OUTREACH_DIR / job_id / "site").resolve()
    if not base.is_dir():
        raise HTTPException(404, "Pages have not been built for this batch.")
    target = (base / path).resolve() if path else base
    if not target.is_relative_to(base):
        raise HTTPException(404, "Not found.")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(404, "Not found.")
    media = "text/html" if target.suffix == ".html" else None
    return FileResponse(str(target), media_type=media)

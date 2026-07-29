"""Phase 4: personalized voice notes at scale.

Upload leads (CSV or JSON) + a message template with {variables} → a batch job
renders one audio file per lead on the language-appropriate engine. Progress is
polled; results download individually or as one zip.
"""
import csv
import io
import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from .. import db, playerpage
from ..audio.chunking import synthesize_chunked
from ..audio.post import post_process
from ..audio.qc import qc_note
from ..config import DATA_DIR
from ..engines import engine_for_language, ensure_active

router = APIRouter(prefix="/outreach", tags=["outreach"])

OUTREACH_DIR = DATA_DIR / "outreach"
VAR_RE = re.compile(r"\{(\w+)\}")

_worker_lock = threading.Lock()  # one batch renders at a time (single GPU)


def render_template(template: str, lead: dict) -> str:
    """A column the lead does not have at all is an error; a column that is
    present but empty renders as nothing, tidied so "Hi {name}," reads "Hi,"."""
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in lead:
            missing.append(key)
            return ""
        return str(lead.get(key) or "").strip()

    text = VAR_RE.sub(sub, template)
    if missing:
        raise ValueError(f"Lead is missing values for: {', '.join(sorted(set(missing)))}")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"^[ \t]+", "", text, flags=re.MULTILINE)
    return text.strip()


# OutreachIQ's fixed export layout; some exports arrive without the header row.
OUTREACHIQ_COLUMNS = [
    "name", "industry", "city", "country", "website", "phone", "rating",
    "review_count", "score", "priority", "score_reason", "brand_gap",
    "outreach_subject", "status", "contact_email", "decision_maker",
    "linkedin_url", "date_added", "date_scored", "date_sent",
    "google_maps_url", "notes",
]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _looks_like_data(cells: list[str]) -> bool:
    """Real header rows never contain URLs, emails, or pure numbers."""
    for cell in cells:
        c = (cell or "").strip()
        if "http://" in c or "https://" in c or "maps.google" in c:
            return True
        if _EMAIL_RE.match(c):
            return True
        if c and re.fullmatch(r"-?\d+(\.\d+)?", c):
            return True
    return False


def parse_leads(raw: bytes, filename: str) -> tuple[list[dict], str | None]:
    text = raw.decode("utf-8-sig", errors="replace")
    looks_like_json = filename.lower().endswith(".json") or text.lstrip().startswith(("[", "{"))
    if looks_like_json:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("JSON leads must be a list of objects.")
        return [dict(x) for x in data], None

    note = None
    first = next(csv.reader(io.StringIO(text)), None)
    if first and _looks_like_data(first):
        # OutreachIQ exports vary between 20 and 22 columns (trailing
        # google_maps_url/notes are sometimes dropped); slice the layout to fit.
        if len(OUTREACHIQ_COLUMNS) - 2 <= len(first) <= len(OUTREACHIQ_COLUMNS):
            fieldnames = OUTREACHIQ_COLUMNS[: len(first)]
            rows = list(csv.DictReader(io.StringIO(text), fieldnames=fieldnames))
            note = "This file has no header row. Recognized the OutreachIQ format and loaded all rows."
        else:
            raise ValueError(
                "The first line of this CSV looks like a lead, not column names. "
                "Add a header line with column names, or use Paste raw info and let AI extract the leads."
            )
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("The CSV has no data rows.")
    return [
        {(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
        for r in rows
    ], note


AUTO_SKIP_STATUSES = {"sent", "skip", "skipped"}


def apply_filters(
    rows: list[dict],
    filter_column: str | None,
    filter_value: str | None,
    include_handled: bool = False,
) -> tuple[list[dict], int, int]:
    """Returns (kept, auto_skipped_count, filtered_out_count).

    Auto-skip drops rows already handled in the source tool (status sent/skip)
    unless include_handled is set (deliberate follow-up to an earlier campaign).
    """
    auto_skipped = 0
    kept: list[dict] = []
    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        if status in AUTO_SKIP_STATUSES and not include_handled:
            auto_skipped += 1
        else:
            kept.append(row)
    filtered_out = 0
    if filter_column and filter_value:
        before = len(kept)
        kept = [
            r for r in kept
            if str(r.get(filter_column, "")).strip().lower() == filter_value.strip().lower()
        ]
        filtered_out = before - len(kept)
    return kept, auto_skipped, filtered_out


async def _read_leads(
    leads: UploadFile | None, leads_text: str | None
) -> tuple[list[dict], str | None]:
    if leads is not None:
        return parse_leads(await leads.read(), leads.filename or "leads.csv")
    if leads_text and leads_text.strip():
        return parse_leads(leads_text.encode("utf-8"), "pasted.csv")
    raise ValueError("Provide a leads file or paste the leads as text.")


def _run_job(job_id: str) -> None:
    with _worker_lock:
        job = db.get_outreach_job(job_id)
        if not job:
            return
        if job["status"] == "stopping":
            # Stopped while still waiting for the GPU: finalize without rendering.
            db.update_outreach_job(job_id, status="stopped")
            return
        if job["status"] not in ("queued",):
            return
        db.update_outreach_job(job_id, status="running")
        job_dir = OUTREACH_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        voice = db.get_voice(job["voice_id"])
        if not voice:
            db.update_outreach_job(job_id, status="failed")
            return
        engine_name = engine_for_language(job["language"])
        try:
            engine = ensure_active(engine_name)
            profile = engine.clone([Path(p) for p in db.voice_refs(voice)])
        except Exception:
            # Any crash here (engine switch, worker spawn, import, bad reference)
            # must mark the job failed — a stuck "running" job can't be deleted.
            db.update_outreach_job(job_id, status="failed")
            return

        done = failed = 0
        stopped = False
        for item in db.list_outreach_items(job_id):
            if item["status"] != "pending":
                continue
            # A stop request lands between notes: the current one finishes,
            # the rest never render.
            current = db.get_outreach_job(job_id)
            if current and current["status"] == "stopping":
                stopped = True
                break
            wav_path = job_dir / f"{item['id']}.wav"
            try:
                synthesize_chunked(
                    engine, profile, item["text"], job["language"], wav_path
                )
                final = post_process(wav_path, job["format"], job["format"] == "mp3")
                db.update_outreach_item(item["id"], "done", output_path=final)
                db.set_outreach_item_qc(item["id"], qc_note(Path(final), item["text"]))
                done += 1
            except Exception as e:  # keep the batch going past a bad row
                db.update_outreach_item(item["id"], "failed", error=str(e)[:300])
                failed += 1
            db.update_outreach_job(job_id, done=done, failed=failed)
        if stopped:
            db.update_outreach_job(job_id, status="stopped")
        else:
            db.update_outreach_job(job_id, status="done" if failed < job["total"] else "failed")


@router.post("/preview")
async def preview(
    template: str = Form(""),
    leads: UploadFile | None = File(None),
    leads_text: str | None = Form(None),
    filter_column: str | None = Form(None),
    filter_value: str | None = Form(None),
    include_handled: bool = Form(False),
):
    """Parse the leads, apply skips and filters, and show what a batch would
    do, before anything renders."""
    try:
        rows, note = await _read_leads(leads, leads_text)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, f"Could not read leads: {e}")

    columns = sorted({k for r in rows for k in r.keys() if k})
    kept, auto_skipped, filtered_out = apply_filters(
        rows, filter_column, filter_value, include_handled
    )

    template_vars = sorted(set(VAR_RE.findall(template))) if template else []
    missing_vars = [v for v in template_vars if v not in columns]
    example = None
    example_error = None
    rendered: list[dict] = []
    if template and kept and not missing_vars:
        try:
            example = render_template(template, kept[0])
        except ValueError as e:
            example_error = str(e)
        # The full set of finished messages, so the UI can show that the
        # template writes itself into every lead's message.
        for row in kept[:100]:
            try:
                rendered.append({"lead": row, "text": render_template(template, row)})
            except ValueError as e:
                rendered.append({"lead": row, "error": str(e)})

    return {
        "note": note,
        "columns": columns,
        "total_rows": len(rows),
        "auto_skipped": auto_skipped,
        "filtered_out": filtered_out,
        "will_render": len(kept),
        "template_variables": template_vars,
        "missing_variables": missing_vars,
        "example": example,
        "example_error": example_error,
        "rendered": rendered,
        # The kept rows themselves, so the UI can hand them to AI drafting
        # without a second parse (100-lead drafting cap).
        "rows": kept[:100],
    }


@router.post("/jobs")
async def create_job(
    name: str = Form(...),
    template: str = Form(""),
    voice_id: str = Form(...),
    language: str = Form("pt"),
    format: str = Form("mp3"),
    leads: UploadFile | None = File(None),
    leads_text: str | None = Form(None),
    filter_column: str | None = Form(None),
    filter_value: str | None = Form(None),
    drafted_json: str | None = Form(None),
    include_handled: bool = Form(False),
):
    if format not in ("wav", "mp3"):
        raise HTTPException(400, "format must be wav or mp3")
    if not db.get_voice(voice_id):
        raise HTTPException(404, f"Voice '{voice_id}' not found.")

    items: list[tuple[str, str]] = []
    if drafted_json:
        # Drafted mode: the UI already has one reviewed message per lead.
        try:
            drafted = json.loads(drafted_json)
            for entry in drafted:
                text = str(entry["text"]).strip()
                if text:
                    items.append((json.dumps(entry.get("lead", {}), ensure_ascii=False), text))
        except (json.JSONDecodeError, KeyError, TypeError):
            raise HTTPException(400, "drafted_json must be a list of {lead, text} objects.")
        if not items:
            raise HTTPException(400, "No drafted messages to render.")
        template = template or "[AI drafted]"
    else:
        if not template.strip():
            raise HTTPException(400, "A message template is required.")
        try:
            rows, _note = await _read_leads(leads, leads_text)
        except (ValueError, json.JSONDecodeError) as e:
            raise HTTPException(400, f"Could not read leads: {e}")
        kept, _auto_skipped, _filtered_out = apply_filters(
            rows, filter_column, filter_value, include_handled
        )
        if not kept:
            raise HTTPException(400, "No leads left after skips and filters.")
        errors: list[str] = []
        for i, lead in enumerate(kept):
            try:
                items.append((json.dumps(lead, ensure_ascii=False), render_template(template, lead)))
            except ValueError as e:
                errors.append(f"row {i + 1}: {e}")
        if errors:
            raise HTTPException(400, "Template/lead mismatch: " + "; ".join(errors[:5]))

    if len(items) > 500:
        raise HTTPException(400, "Max 500 leads per job.")

    job = db.insert_outreach_job(name, template, voice_id, language, format, items)
    threading.Thread(target=_run_job, args=(job["id"],), daemon=True).start()
    return job


@router.get("/jobs")
def jobs():
    return db.list_outreach_jobs()


@router.get("/jobs/{job_id}")
def job_detail(job_id: str):
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    job["items"] = db.list_outreach_items(job_id)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Permanent: removes the batch, its leads, and every audio file it made."""
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "This batch is still rendering. Wait for it to finish first.")
    db.delete_outreach_job(job_id)
    job_dir = OUTREACH_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"deleted": job_id}


@router.get("/items/{item_id}/audio")
def item_audio(item_id: str):
    item = db.get_outreach_item(item_id)
    if item and item["output_path"]:
        path = Path(item["output_path"])
        if path.exists():
            media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
            return FileResponse(str(path), media_type=media, filename=path.name)
    raise HTTPException(404, "Item audio not found.")


def _rerender_one(item_id: str) -> None:
    with _worker_lock:
        item = db.get_outreach_item(item_id)
        if not item or item["status"] != "pending":
            return
        job = db.get_outreach_job(item["job_id"])
        voice = db.get_voice(job["voice_id"]) if job else None
        if not job or not voice:
            db.update_outreach_item(item_id, "failed", error="Job or voice no longer exists.")
            return
        db.update_outreach_job(job["id"], status="running")
        job_dir = OUTREACH_DIR / job["id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            engine = ensure_active(engine_for_language(job["language"]))
            profile = engine.clone([Path(p) for p in db.voice_refs(voice)])
            wav_path = job_dir / f"{item_id}.wav"
            synthesize_chunked(engine, profile, item["text"], job["language"], wav_path)
            final = post_process(wav_path, job["format"], job["format"] == "mp3")
            db.update_outreach_item(item_id, "done", output_path=final)
            db.set_outreach_item_qc(item_id, qc_note(Path(final), item["text"]))
        except Exception as e:
            db.update_outreach_item(item_id, "failed", error=str(e)[:300])
        items = db.list_outreach_items(job["id"])
        done = sum(1 for i in items if i["status"] == "done")
        failed = sum(1 for i in items if i["status"] == "failed")
        db.update_outreach_job(
            job["id"], done=done, failed=failed,
            status="done" if failed < job["total"] else "failed",
        )
        # Keep the built pages in sync with the fresh take.
        if (job_dir / "site").exists():
            business = db.get_setting("business_profile", {})
            try:
                playerpage.build_site(db.get_outreach_job(job["id"]), items, business)
            except Exception:
                pass  # pages can be rebuilt manually from the UI


@router.post("/items/{item_id}/rerender")
def rerender_item(item_id: str):
    """Replace one lead's take with a fresh render. Takes vary; this is the
    cure for a stutter, a repeat, or a long pause in a single note."""
    item = db.get_outreach_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found.")
    job = db.get_outreach_job(item["job_id"])
    if not job:
        raise HTTPException(404, "Job not found.")
    if job["status"] in ("queued", "running", "stopping"):
        raise HTTPException(409, "This batch is busy. Wait for it to finish first.")
    db.update_outreach_item(item_id, "pending")
    threading.Thread(target=_rerender_one, args=(item_id,), daemon=True).start()
    return {"item_id": item_id, "job_id": job["id"], "status": "pending"}


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    """Graceful stop: the note rendering right now finishes, the rest do not."""
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job["status"] not in ("queued", "running"):
        raise HTTPException(409, "This batch is not running.")
    db.update_outreach_job(job_id, status="stopping")
    return db.get_outreach_job(job_id)


@router.get("/jobs/{job_id}/download")
def job_zip(job_id: str):
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    items = [i for i in db.list_outreach_items(job_id) if i["status"] == "done"]
    if not items:
        raise HTTPException(400, "No finished items to download yet.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for item in items:
            path = Path(item["output_path"])
            if not path.exists():
                continue
            lead = item["lead"]
            label = str(lead.get("name") or lead.get("email") or item["id"])
            safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in label).strip()
            z.write(path, f"{safe or item['id']}{path.suffix}")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{job["name"] or job_id}.zip"'},
    )


@router.post("/jobs/{job_id}/site")
def build_site(job_id: str):
    """Build (or cleanly rebuild) the static player page bundle for a finished batch."""
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "This batch is still rendering. Wait for it to finish first.")
    items = db.list_outreach_items(job_id)
    if not any(i["status"] == "done" for i in items):
        raise HTTPException(400, "No finished items to build pages for.")
    profile = db.get_setting("business_profile", {})
    result = playerpage.build_site(job, items, profile)
    db.update_outreach_job(job_id, site_built_at=time.time())
    return {
        "job_id": job_id,
        "pages": result["pages"],
        "skipped": result["skipped"],
        "warnings": result["warnings"],
        "preview_url": f"/sites/{job_id}/",
    }


@router.get("/jobs/{job_id}/site/download")
def site_zip(job_id: str):
    job = db.get_outreach_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    site_dir = OUTREACH_DIR / job_id / "site"
    if not site_dir.exists():
        raise HTTPException(404, "Pages have not been built for this batch yet.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "README.txt",
            "Extract this whole zip before opening anything.\r\n"
            "Each lead's page lives in its own folder next to its audio file;\r\n"
            "opening pages from inside the zip breaks the links between them.\r\n"
            "To publish, upload the extracted folder to any static host.\r\n",
        )
        for path in sorted(site_dir.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(site_dir).as_posix())
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{job["name"] or job_id}-pages.zip"'
        },
    )

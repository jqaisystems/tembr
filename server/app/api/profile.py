"""Business profile + drafting settings, usage, and the draft endpoint."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..drafting import (
    BudgetExceeded,
    DraftingError,
    draft_messages,
    extract_leads,
    get_drafting_settings,
    suggest_templates,
    usage_summary,
)

router = APIRouter(tags=["profile"])

PROFILE_FIELDS = [
    "business_name", "one_liner", "what_we_do", "tone_of_voice",
    "target_customer", "website", "linkedin", "other_links",
    "email", "cta_label", "phone", "website2",
    "primary_language", "secondary_languages", "cv_text", "cv_link",
]


class Profile(BaseModel):
    business_name: str = ""
    one_liner: str = ""
    what_we_do: str = ""
    tone_of_voice: str = ""
    target_customer: str = ""
    website: str = ""
    linkedin: str = ""
    other_links: str = ""
    email: str = ""
    cta_label: str = ""
    phone: str = ""
    website2: str = ""
    primary_language: str = "en"
    secondary_languages: list[str] = Field(default_factory=list)
    cv_text: str = ""
    cv_link: str = ""


@router.get("/profile")
def get_profile():
    # Merge over defaults so profiles saved before new fields existed still return them.
    return {**Profile().model_dump(), **db.get_setting("business_profile", {})}


@router.put("/profile")
def put_profile(profile: Profile):
    db.set_setting("business_profile", profile.model_dump())
    return profile.model_dump()


@router.post("/profile/cv")
async def upload_cv(file: UploadFile = File(...)):
    """Load a CV or company document into the profile as drafting grounding."""
    suffix = (file.filename or "").lower().rsplit(".", 1)
    ext = f".{suffix[1]}" if len(suffix) == 2 else ""
    if ext not in (".txt", ".md"):
        raise HTTPException(
            400, "Paste the text instead, or upload a .txt or .md file. PDFs are not readable here."
        )
    text = (await file.read()).decode("utf-8", errors="replace")[:20000]
    stored = {**Profile().model_dump(), **db.get_setting("business_profile", {})}
    stored["cv_text"] = text.strip()
    db.set_setting("business_profile", stored)
    return stored


class DraftingSettings(BaseModel):
    order: list[str]
    enabled: dict[str, bool]
    budgets: dict[str, dict[str, int | None]]
    models: dict[str, dict[str, str]] = {}


@router.get("/drafting/settings")
def get_draft_settings():
    return get_drafting_settings()


@router.put("/drafting/settings")
def put_draft_settings(settings: DraftingSettings):
    db.set_setting("drafting", settings.model_dump())
    return get_drafting_settings()


@router.get("/drafting/usage")
def get_drafting_usage():
    return {"usage": usage_summary(), "settings": get_drafting_settings()}


MAINTENANCE_DUE_DAYS = 30


@router.get("/maintenance")
def get_maintenance():
    import time

    last_run = db.get_setting("maintenance_last_run")  # unix seconds or None
    due = last_run is None or (time.time() - last_run) > MAINTENANCE_DUE_DAYS * 86400
    return {"last_run": last_run, "due": due, "interval_days": MAINTENANCE_DUE_DAYS}


class MaintenanceUpdate(BaseModel):
    last_run: float


@router.put("/maintenance")
def put_maintenance(update: MaintenanceUpdate):
    db.set_setting("maintenance_last_run", update.last_run)
    return get_maintenance()


class DraftRequest(BaseModel):
    leads: list[dict] = Field(..., min_length=1, max_length=100)
    language: str = "pt"
    instructions: str = ""
    override_budget: bool = False


@router.post("/outreach/draft")
def draft(req: DraftRequest):
    profile = db.get_setting("business_profile", {})
    try:
        return draft_messages(
            req.leads, profile, req.instructions, req.language, req.override_budget
        )
    except BudgetExceeded as e:
        raise HTTPException(429, str(e))
    except DraftingError as e:
        raise HTTPException(400, str(e))


class ExtractRequest(BaseModel):
    raw_text: str = Field(..., min_length=10)
    override_budget: bool = False


@router.post("/outreach/extract")
def extract(req: ExtractRequest):
    """Raw notes in, a clean lead table out, via the CLI drafting providers."""
    try:
        return extract_leads(req.raw_text, req.override_budget)
    except BudgetExceeded as e:
        raise HTTPException(429, str(e))
    except DraftingError as e:
        raise HTTPException(400, str(e))


class SuggestTemplatesRequest(BaseModel):
    columns: list[str] = Field(..., min_length=1)
    sample_rows: list[dict] = Field(default_factory=list, max_length=3)
    language: str = "en"
    offer: str = ""
    override_budget: bool = False


@router.post("/outreach/suggest-templates")
def suggest(req: SuggestTemplatesRequest):
    profile = db.get_setting("business_profile", {})
    try:
        return suggest_templates(
            req.columns, req.sample_rows, profile, req.language, req.offer, req.override_budget
        )
    except BudgetExceeded as e:
        raise HTTPException(429, str(e))
    except DraftingError as e:
        raise HTTPException(400, str(e))

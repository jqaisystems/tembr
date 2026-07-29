"""AI drafting through locally installed CLI subscriptions.

No API keys anywhere: the CLIs (codex primary, claude fallback) hold their
own auth and are simply found on PATH. Every call batches ALL leads into one
CLI invocation to amortize startup cost, records token usage in the local
ledger, and respects per-provider budgets. Only text drafting leaves the
machine; voice rendering is always local.
"""
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from . import db
from .config import TMP_DIR

PROVIDERS = ["codex-cli", "claude-cli"]
CLI_TIMEOUT_S = 240

DEFAULT_SETTINGS = {
    "order": ["codex-cli", "claude-cli"],
    "enabled": {"codex-cli": True, "claude-cli": True},
    "budgets": {  # weekly/monthly output+input token caps per provider; null = no cap
        "codex-cli": {"weekly": None, "monthly": None},
        "claude-cli": {"weekly": None, "monthly": None},
    },
    # Empty string = use the CLI's own configured default.
    "models": {
        "codex-cli": {"model": "", "effort": ""},
        "claude-cli": {"model": ""},
    },
}

LANGUAGE_NAMES = {
    "en": "English", "pt": "European Portuguese (Portugal, never Brazilian)",
    "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
}

STRINGS_SCHEMA = {
    "type": "object",
    "properties": {"messages": {"type": "array", "items": {"type": "string"}}},
    "required": ["messages"],
    "additionalProperties": False,
}

LEAD_FIELDS = ["name", "business", "email", "phone", "website", "context", "notes"]

LEADS_SCHEMA = {
    "type": "object",
    "properties": {
        "leads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {f: {"type": "string"} for f in LEAD_FIELDS},
                "required": LEAD_FIELDS,
                "additionalProperties": False,
            },
        }
    },
    "required": ["leads"],
    "additionalProperties": False,
}


class DraftingError(Exception):
    pass


class BudgetExceeded(DraftingError):
    pass


def get_drafting_settings() -> dict:
    saved = db.get_setting("drafting", {})
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    for key in merged:
        if key in saved:
            if isinstance(merged[key], dict):
                merged[key].update(saved[key])
            else:
                merged[key] = saved[key]
    return merged


def usage_summary() -> dict:
    now = time.time()
    week = {u["provider"]: u for u in db.drafting_usage_since(now - 7 * 86400)}
    month = {u["provider"]: u for u in db.drafting_usage_since(now - 30 * 86400)}
    return {"week": week, "month": month}


def _check_budget(provider: str, settings: dict, override: bool) -> str | None:
    """Returns a warning string when near/over budget; raises when over and
    not overridden."""
    budgets = settings["budgets"].get(provider, {})
    summary = usage_summary()
    for period, seconds in (("weekly", 7 * 86400), ("monthly", 30 * 86400)):
        cap = budgets.get(period)
        if not cap:
            continue
        used_row = db.drafting_usage_since(time.time() - seconds)
        used = sum(
            (r["input_tokens"] or 0) + (r["output_tokens"] or 0)
            for r in used_row
            if r["provider"] == provider
        )
        if used >= cap and not override:
            raise BudgetExceeded(
                f"{provider} is over its {period} budget ({used:,} of {cap:,} tokens). "
                "Raise the budget in Settings or confirm the override."
            )
        if used >= cap * 0.8:
            return f"{provider} has used {used:,} of its {period} budget of {cap:,} tokens."
    _ = summary
    return None


def _build_prompt(leads: list[dict], profile: dict, instructions: str, language: str) -> str:
    lang = LANGUAGE_NAMES.get(language, language)
    profile_lines = "\n".join(
        f"- {label}: {profile[key]}"
        for key, label in (
            ("business_name", "Business"),
            ("one_liner", "In one line"),
            ("what_we_do", "What we do"),
            ("tone_of_voice", "Tone of voice"),
            ("target_customer", "Target customer"),
            ("website", "Website"),
            ("linkedin", "LinkedIn"),
            ("other_links", "Other links"),
            ("cv_link", "CV link"),
        )
        if profile.get(key)
    ) or "- (no profile saved)"
    cv_block = ""
    if profile.get("cv_text"):
        cv_block = f"\n\nSender background (CV):\n{profile['cv_text'][:3000]}"
    offer_block = "none"
    if instructions.strip():
        offer_block = (
            f"{instructions.strip()}\n"
            "Write the message around this offer. If it includes a secondary "
            "service, mention that briefly at the end as a light P.S., one sentence."
        )
    return f"""You write short spoken voice-note scripts for business outreach. The sender will record-quality text-to-speech them in their own cloned voice.

Sender's business profile:
{profile_lines}{cv_block}

The sender's offer and extra instructions for this batch: {offer_block}

Leads, as JSON:
{json.dumps(leads, ensure_ascii=False, indent=2)}

Write ONE personalized voice-note message PER lead, in {lang}. Spoken-word style, 40 to 70 words each (15 to 25 seconds aloud). Rules:
- Sound like a real person talking: warm, direct, matched to the sender's tone of voice.
- Personalize from each lead's own fields (brand_gap, score_reason, outreach_subject, notes and similar are the best material). Never invent facts about the lead.
- Never use em dashes. Use a comma, a colon, or a new sentence instead.
- No "I hope this finds you well", no filler, no lists, no sign-off blocks. Natural speech only.
- End each message with a light, specific call to a short conversation.

Return ONLY a JSON array of strings, one message per lead, in the same order as the leads. No markdown fences, no commentary."""


def _extract_json_list(text: str) -> list:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise DraftingError("The model did not return a JSON array.")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise DraftingError("The model returned JSON that is not an array.")
    return data


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _run_codex(
    prompt: str,
    model_cfg: dict | None = None,
    schema: dict | None = None,
    key: str = "messages",
) -> tuple[list, int, int, bool]:
    exe = shutil.which("codex")
    if not exe:
        raise DraftingError("Codex CLI is not installed or not on PATH.")
    out_file = TMP_DIR / f"draft_{uuid.uuid4().hex[:8]}.txt"
    schema_file = TMP_DIR / f"draft_schema_{uuid.uuid4().hex[:8]}.json"
    # OpenAI response schemas must be type "object" at the top level.
    schema_file.write_text(json.dumps(schema or STRINGS_SCHEMA), encoding="utf-8")
    args = [
        exe, "exec", "--skip-git-repo-check", "-s", "read-only",
        "--output-schema", str(schema_file), "-o", str(out_file),
    ]
    if model_cfg and model_cfg.get("model"):
        args += ["-m", model_cfg["model"]]
    if model_cfg and model_cfg.get("effort"):
        args += ["-c", f'model_reasoning_effort="{model_cfg["effort"]}"']
    args.append("-")
    try:
        result = subprocess.run(
            args,
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=CLI_TIMEOUT_S,
            cwd=str(TMP_DIR),
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[-400:]
            raise DraftingError(f"Codex CLI failed: {err}")
        raw = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        if not raw.strip():
            raw = result.stdout.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw.strip())
            if isinstance(parsed, dict) and isinstance(parsed.get(key), list):
                messages = parsed[key]
            else:
                messages = _extract_json_list(raw)
        except json.JSONDecodeError:
            messages = _extract_json_list(raw)
        # Token usage: look for usage hints in stdout events; estimate otherwise.
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        m = re.search(r'"input_tokens"\s*:\s*(\d+).*?"output_tokens"\s*:\s*(\d+)', stdout_text, re.DOTALL)
        if m:
            return messages, int(m.group(1)), int(m.group(2)), False
        return messages, _estimate_tokens(prompt), _estimate_tokens(raw), True
    finally:
        out_file.unlink(missing_ok=True)
        schema_file.unlink(missing_ok=True)


def _run_claude(
    prompt: str,
    model_cfg: dict | None = None,
    schema: dict | None = None,
    key: str = "messages",
) -> tuple[list, int, int, bool]:
    # Claude CLI has no schema enforcement; the prompt asks for a bare JSON
    # array and _extract_json_list pulls it out. schema/key kept for symmetry.
    exe = shutil.which("claude")
    if not exe:
        raise DraftingError("Claude CLI is not installed or not on PATH.")
    args = [exe, "-p", "--output-format", "json"]
    if model_cfg and model_cfg.get("model"):
        args += ["--model", model_cfg["model"]]
    result = subprocess.run(
        args,
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=CLI_TIMEOUT_S,
        cwd=str(TMP_DIR),
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")[-400:]
        raise DraftingError(f"Claude CLI failed: {err}")
    payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
    text = payload.get("result", "")
    messages = _extract_json_list(text)
    usage = payload.get("usage") or {}
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    if inp or out:
        return messages, inp, out, False
    return messages, _estimate_tokens(prompt), _estimate_tokens(text), True


_RUNNERS = {"codex-cli": _run_codex, "claude-cli": _run_claude}


def _unwrap_double_encoded(value: list) -> list:
    """Models sometimes satisfy the array schema with ONE string that is itself
    a JSON-encoded array. Unwrap that case so every caller sees real items."""
    if len(value) == 1 and isinstance(value[0], str):
        s = value[0].strip()
        if s.startswith("["):
            try:
                inner = json.loads(s)
                if isinstance(inner, list) and inner:
                    return inner
            except json.JSONDecodeError:
                pass
    return value


def _run_chain(prompt: str, schema: dict, key: str, validate, override_budget: bool) -> dict:
    """Try each enabled provider in order; `validate(list) -> list` may raise
    DraftingError to reject a provider's output and move to the next."""
    settings = get_drafting_settings()
    errors: list[str] = []
    warning = None
    for provider in settings["order"]:
        if provider not in _RUNNERS or not settings["enabled"].get(provider, False):
            continue
        try:
            warning = _check_budget(provider, settings, override_budget)
        except BudgetExceeded as e:
            errors.append(str(e))
            continue
        try:
            model_cfg = settings.get("models", {}).get(provider)
            value, inp, out, estimated = _RUNNERS[provider](prompt, model_cfg, schema, key)
            value = validate(_unwrap_double_encoded(value))
        except (DraftingError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f"[drafting] {provider} failed: {str(e)[:400]}")
            errors.append(f"{provider}: {e}")
            continue
        db.insert_drafting_usage(provider, inp, out, estimated, len(value))
        return {
            "provider": provider,
            "value": value,
            "input_tokens": inp,
            "output_tokens": out,
            "estimated": estimated,
            "budget_warning": warning,
        }

    enabled_any = any(settings["enabled"].get(p) for p in settings["order"])
    if not enabled_any:
        raise DraftingError("All drafting providers are disabled in Settings.")
    raise DraftingError("Drafting failed. " + " | ".join(errors[-3:]))


def draft_messages(
    leads: list[dict],
    profile: dict,
    instructions: str = "",
    language: str = "pt",
    override_budget: bool = False,
) -> dict:
    prompt = _build_prompt(leads, profile, instructions, language)

    def validate(value: list) -> list[str]:
        messages = [str(m) for m in value]
        if len(messages) != len(leads):
            raise DraftingError(
                f"returned {len(messages)} messages for {len(leads)} leads."
            )
        return messages

    result = _run_chain(prompt, STRINGS_SCHEMA, "messages", validate, override_budget)
    result["messages"] = result.pop("value")
    return result


def extract_leads(raw_text: str, override_budget: bool = False) -> dict:
    prompt = f"""You extract business leads from raw notes for a voice outreach tool.

Raw text from the sender:
{raw_text.strip()[:12000]}

Extract every distinct lead (a person or business worth contacting). For each lead fill exactly these string fields, using an empty string when the text does not say:
- name: the contact person's first name, or the business name when no person is named
- business: the company or business name
- email: email address found in the text
- phone: phone number found in the text
- website: website found in the text
- context: the single most personalization-worthy fact about this lead, one short sentence, taken only from the text
- notes: any other useful detail, short

Never invent information that is not in the text. Never use em dashes anywhere.

Return ONLY JSON: an array of lead objects with exactly those keys. No markdown fences, no commentary."""

    def validate(value: list) -> list[dict]:
        leads = []
        for item in value:
            if not isinstance(item, dict):
                continue
            lead = {f: str(item.get(f, "") or "").strip() for f in LEAD_FIELDS}
            if any(lead.values()):
                leads.append(lead)
        if not leads:
            raise DraftingError("no leads could be extracted from the text.")
        return leads

    result = _run_chain(prompt, LEADS_SCHEMA, "leads", validate, override_budget)
    result["leads"] = result.pop("value")
    return result


def suggest_templates(
    columns: list[str],
    sample_rows: list[dict],
    profile: dict,
    language: str = "en",
    offer: str = "",
    override_budget: bool = False,
) -> dict:
    lang = LANGUAGE_NAMES.get(language, language)
    profile_lines = "\n".join(
        f"- {label}: {profile[key]}"
        for key, label in (
            ("business_name", "Business"),
            ("one_liner", "In one line"),
            ("what_we_do", "What we do"),
            ("tone_of_voice", "Tone of voice"),
        )
        if profile.get(key)
    ) or "- (no profile saved)"
    offer_block = ""
    if offer.strip():
        offer_block = (
            f"\nThe sender's offer for THIS batch (write every template around it): {offer.strip()}\n"
            "If the offer includes a secondary service, mention that briefly at the "
            "end as a light P.S., one sentence.\n"
        )
    prompt = f"""You write reusable spoken voice-note templates for business outreach. The sender records them with text-to-speech in their own cloned voice, one note per lead.

Sender's business profile:
{profile_lines}
{offer_block}
Available variables (the columns of the sender's lead list): {", ".join(columns)}
Example leads:
{json.dumps(sample_rows[:3], ensure_ascii=False, indent=2)}

Write 3 different template options in {lang}, each taking a different angle (for example: direct value, curious question, specific observation). Each template:
- 40 to 70 spoken words (15 to 25 seconds aloud), natural speech, warm and direct.
- Uses variables ONLY from the list above, written as {{variable}} in curly braces.
- Personalizes with the variables that carry the most meaning per lead.
- Never uses em dashes. A comma, a colon, or a new sentence instead.
- No "I hope this finds you well", no filler, no sign-off blocks.
- Ends with a light, specific call to a short conversation.

Return ONLY a JSON array of 3 template strings. No markdown fences, no commentary."""

    def validate(value: list) -> list[str]:
        templates = [str(t).strip() for t in value if str(t).strip()]
        if not templates:
            raise DraftingError("no templates returned.")
        return templates[:3]

    result = _run_chain(prompt, STRINGS_SCHEMA, "messages", validate, override_budget)
    result["templates"] = result.pop("value")
    return result

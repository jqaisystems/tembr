import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS voices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    engine TEXT NOT NULL,
    samples TEXT NOT NULL,          -- JSON list of sample file paths
    consent INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    collection TEXT NOT NULL DEFAULT '',   -- free-text folder, like generations.project
    qc TEXT,                               -- JSON from audio.reference.measure_bandwidth
    cleanup TEXT,                          -- JSON: denoise provenance + revert paths
    source TEXT NOT NULL DEFAULT '',       -- script situation the take came from
    updated_at REAL NOT NULL DEFAULT 0,
    window TEXT                            -- JSON: curated conditioning window {path, start_s, end_s, score}
);
CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY,
    voice_id TEXT,
    engine TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    output_path TEXT NOT NULL,
    duration_s REAL,
    elapsed_s REAL,
    created_at REAL NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outreach_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    language TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'mp3',
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | running | done | failed
    total INTEGER NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    lead TEXT NOT NULL,                      -- JSON of the lead's fields
    text TEXT NOT NULL,                      -- rendered message
    output_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
    error TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outreach_items_job ON outreach_items(job_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafting_usage (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated INTEGER NOT NULL DEFAULT 0,
    leads_count INTEGER NOT NULL DEFAULT 0,
    job_id TEXT,
    created_at REAL NOT NULL
);
"""


def init_db() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(generations)")}
        for ddl in (
            "project TEXT NOT NULL DEFAULT ''",
            "name TEXT NOT NULL DEFAULT ''",
            "favorite INTEGER NOT NULL DEFAULT 0",
        ):
            if ddl.split()[0] not in cols:
                c.execute(f"ALTER TABLE generations ADD COLUMN {ddl}")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(outreach_items)")}
        if "slug" not in cols:
            c.execute("ALTER TABLE outreach_items ADD COLUMN slug TEXT")
        if "qc" not in cols:
            c.execute("ALTER TABLE outreach_items ADD COLUMN qc TEXT")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(outreach_jobs)")}
        if "site_built_at" not in cols:
            c.execute("ALTER TABLE outreach_jobs ADD COLUMN site_built_at REAL")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(voices)")}
        for ddl in (
            "favorite INTEGER NOT NULL DEFAULT 0",
            "collection TEXT NOT NULL DEFAULT ''",
            "qc TEXT",
            "cleanup TEXT",
            "source TEXT NOT NULL DEFAULT ''",
            "updated_at REAL NOT NULL DEFAULT 0",
            "window TEXT",
        ):
            if ddl.split()[0] not in cols:
                c.execute(f"ALTER TABLE voices ADD COLUMN {ddl}")
        c.execute("UPDATE voices SET updated_at=created_at WHERE updated_at=0")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def insert_voice(name, description, language, engine, samples, consent, vid=None,
                 collection="", source="", qc=None, cleanup=None, window=None) -> dict:
    # Named columns, not positional: the voices table gains columns over time
    # and a bare VALUES(...) breaks every insert the moment one is added.
    vid = vid or new_id()
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO voices (id, name, description, language, engine, samples, "
            "consent, created_at, favorite, collection, qc, cleanup, source, updated_at, window) "
            "VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)",
            (vid, name, description, language, engine, json.dumps(samples), int(consent),
             now, collection, json.dumps(qc) if qc else None,
             json.dumps(cleanup) if cleanup else None, source, now,
             json.dumps(window) if window else None),
        )
    return get_voice(vid)


def get_voice(vid) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM voices WHERE id=?", (vid,)).fetchone()
    return _voice_dict(row) if row else None


def list_voices() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM voices ORDER BY favorite DESC, created_at DESC"
        ).fetchall()
    return [_voice_dict(r) for r in rows]


def list_voice_collections() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT collection FROM voices WHERE collection != '' ORDER BY collection"
        ).fetchall()
    return [r["collection"] for r in rows]


def set_voice_qc(vid, qc: dict | None) -> None:
    update_voice(vid, qc=json.dumps(qc) if qc else None)


def set_voice_cleanup(vid, data: dict | None) -> None:
    update_voice(vid, cleanup=json.dumps(data) if data else None)


def set_voice_window(vid, data: dict | None) -> None:
    update_voice(vid, window=json.dumps(data) if data else None)


def voice_refs(voice: dict) -> list[str]:
    """The files an engine should condition on, in order.

    The engines read only refs[0], and chatterbox's decoder hears only its
    first ten seconds, so when a curated window exists it leads; the full
    samples follow for any engine that wants more.
    """
    window = voice.get("window")
    if window and window.get("path"):
        return [window["path"], *voice["samples"]]
    return list(voice["samples"])


def delete_voice(vid) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM voices WHERE id=?", (vid,))
    return cur.rowcount > 0


def update_voice(vid, **fields) -> None:
    # Callers must whitelist keys (see api/voices.py); kwargs land in the SQL.
    fields.setdefault("updated_at", time.time())
    keys = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE voices SET {keys} WHERE id=?", (*fields.values(), vid))


def _voice_dict(row) -> dict:
    d = dict(row)
    d["samples"] = json.loads(d["samples"])
    d["consent"] = bool(d["consent"])
    d["favorite"] = bool(d.get("favorite", 0))
    for key in ("qc", "cleanup", "window"):
        d[key] = json.loads(d[key]) if d.get(key) else None
    return d


def insert_generation(
    voice_id, engine, language, text, output_path, duration_s, elapsed_s, gid=None,
    project="", name=""
) -> dict:
    gid = gid or new_id()
    with _conn() as c:
        c.execute(
            "INSERT INTO generations (id, voice_id, engine, language, text, output_path, "
            "duration_s, elapsed_s, created_at, project, name, favorite) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,0)",
            (gid, voice_id, engine, language, text, str(output_path), duration_s, elapsed_s,
             time.time(), project or "", name or ""),
        )
    return get_generation(gid)


def _generation_dict(row) -> dict:
    d = dict(row)
    d["favorite"] = bool(d.get("favorite", 0))
    return d


def get_generation(gid) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM generations WHERE id=?", (gid,)).fetchone()
    return _generation_dict(row) if row else None


def update_generation(gid, **fields) -> None:
    # Callers must whitelist keys (see api/generate.py); kwargs land in the SQL.
    keys = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE generations SET {keys} WHERE id=?", (*fields.values(), gid))


def list_generations(limit=50, project=None) -> list[dict]:
    with _conn() as c:
        if project is not None:
            rows = c.execute(
                "SELECT * FROM generations WHERE project=? ORDER BY created_at DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [_generation_dict(r) for r in rows]


def generation_names_like(base: str) -> list[str]:
    """Existing names that are `base` or `base <number>`, for de-duplicating."""
    with _conn() as c:
        rows = c.execute(
            "SELECT name FROM generations WHERE name = ? OR name LIKE ?",
            (base, f"{base} %"),
        ).fetchall()
    return [r["name"] for r in rows]


def list_generation_projects() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT project FROM generations WHERE project != '' ORDER BY project"
        ).fetchall()
    return [r["project"] for r in rows]


def delete_generation(gid) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM generations WHERE id=?", (gid,))
    return cur.rowcount > 0


# ---------- outreach ----------


def insert_outreach_job(name, template, voice_id, language, fmt, items) -> dict:
    """items: list of (lead_dict_json, rendered_text)."""
    jid = new_id()
    with _conn() as c:
        c.execute(
            "INSERT INTO outreach_jobs (id, name, template, voice_id, language, format, status, total, done, failed, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,0,0,?)",
            (jid, name, template, voice_id, language, fmt, "queued", len(items), time.time()),
        )
        for lead_json, text in items:
            c.execute(
                "INSERT INTO outreach_items (id, job_id, lead, text, status, created_at) VALUES (?,?,?,?,?,?)",
                (new_id(), jid, lead_json, text, "pending", time.time()),
            )
    return get_outreach_job(jid)


def get_outreach_job(jid) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM outreach_jobs WHERE id=?", (jid,)).fetchone()
    return dict(row) if row else None


def list_outreach_jobs(limit=50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM outreach_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_outreach_items(jid) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM outreach_items WHERE job_id=? ORDER BY created_at", (jid,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["lead"] = json.loads(d["lead"])
        d["qc"] = json.loads(d["qc"]) if d.get("qc") else None
        out.append(d)
    return out


def get_outreach_item(item_id) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM outreach_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["lead"] = json.loads(d["lead"])
    d["qc"] = json.loads(d["qc"]) if d.get("qc") else None
    return d


def set_outreach_item_qc(item_id, qc: dict) -> None:
    with _conn() as c:
        c.execute("UPDATE outreach_items SET qc=? WHERE id=?", (json.dumps(qc), item_id))


def update_outreach_item(item_id, status, output_path=None, error=None) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE outreach_items SET status=?, output_path=?, error=? WHERE id=?",
            (status, str(output_path) if output_path else None, error, item_id),
        )


def set_outreach_item_slug(item_id, slug) -> None:
    with _conn() as c:
        c.execute("UPDATE outreach_items SET slug=? WHERE id=?", (slug, item_id))


def delete_outreach_job(jid) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM outreach_items WHERE job_id=?", (jid,))
        cur = c.execute("DELETE FROM outreach_jobs WHERE id=?", (jid,))
    return cur.rowcount > 0


def update_outreach_job(jid, **fields) -> None:
    keys = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE outreach_jobs SET {keys} WHERE id=?", (*fields.values(), jid))


# ---------- settings & drafting usage ----------


def get_setting(key: str, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def insert_drafting_usage(provider, input_tokens, output_tokens, estimated, leads_count, job_id=None) -> None:
    # Named columns, not positional: see insert_voice.
    with _conn() as c:
        c.execute(
            "INSERT INTO drafting_usage (id, provider, input_tokens, output_tokens, "
            "estimated, leads_count, job_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_id(), provider, input_tokens, output_tokens, int(estimated), leads_count, job_id, time.time()),
        )


def drafting_usage_since(since_ts: float) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT provider, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, SUM(leads_count) AS leads, "
            "MAX(estimated) AS any_estimated "
            "FROM drafting_usage WHERE created_at >= ? GROUP BY provider",
            (since_ts,),
        ).fetchall()
    return [dict(r) for r in rows]

"""Static player page export: one branded "voice business card" page per outreach lead.

Builds data/outreach/{job_id}/site/ as a fully self-contained folder:
  site/index.html          private overview for the studio owner
  site/{slug}/index.html   public page for one lead
  site/{slug}/message.mp3  copy of the rendered audio (relative sibling)

No dependencies beyond the stdlib; HTML comes from string.Template. The folder can be
previewed via the local API or dragged onto any static host unchanged.
"""
from __future__ import annotations

import hashlib
import html
import re
import shutil
import time
import unicodedata
from pathlib import Path
from string import Template
from urllib.parse import quote

from . import db
from .config import DATA_DIR

OUTREACH_DIR = DATA_DIR / "outreach"
BRAND_DIR = Path(__file__).parent / "assets" / "brand"

_LOGO_CACHE: dict[str, str] = {}

# Brand endpoints for the waveform gradient (teal -> cyan, official guide values).
_TEAL = (0x00, 0xA7, 0x9D)
_CYAN = (0x00, 0x95, 0xDA)

STRINGS = {
    "en": {
        "eyebrow": "A voice message for",
        "cta": "Reply by email",
        "subject": "Re: voice message",
        "sent_by": "Sent personally by",
        "play": "Play the message",
        "pause": "Pause the message",
        "built": "built",
        "pages": "pages",
        "lead": "Lead",
        "open": "Open page",
    },
    "pt": {
        "eyebrow": "Uma mensagem de voz para",
        "cta": "Responder por email",
        "subject": "Re: mensagem de voz",
        "sent_by": "Enviado pessoalmente por",
        "play": "Ouvir a mensagem",
        "pause": "Pausar a mensagem",
        "built": "criado",
        "pages": "páginas",
        "lead": "Contacto",
        "open": "Abrir página",
    },
}


def _load_brand(name: str) -> str:
    """The logo and favicon a built page carries.

    Drop your own `logo.svg` and `mark.svg` into `assets/brand/custom/` and
    your pages wear your brand instead of the Tembr default. That folder is
    ignored by git, so a private brand never travels with the code.
    """
    if name not in _LOGO_CACHE:
        custom = BRAND_DIR / "custom" / name
        path = custom if custom.exists() else BRAND_DIR / name
        _LOGO_CACHE[name] = path.read_text(encoding="utf-8")
    return _LOGO_CACHE[name]


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return ascii_text[:40].strip("-")


def _lead_name(lead: dict) -> str:
    name = (lead.get("name") or lead.get("business") or "").strip()
    if not name and lead.get("email"):
        name = lead["email"].split("@")[0]
    return name or "you"


def item_slug(item: dict) -> str:
    base = slugify(_lead_name(item["lead"])) or "lead"
    return f"{base}-{item['id'][:6]}"


def _bars(item_id: str, n: int = 44) -> str:
    """Deterministic pseudo-waveform: heights hashed from the item id, colors
    interpolated across the brand gradient so a fully played message shows it."""
    raw = hashlib.sha256(item_id.encode()).digest()
    while len(raw) < n:
        raw += hashlib.sha256(raw).digest()
    out = []
    for i in range(n):
        h = 22 + (raw[i] % 79)
        t = i / (n - 1)
        color = "#%02X%02X%02X" % tuple(
            round(a + (b - a) * t) for a, b in zip(_TEAL, _CYAN)
        )
        out.append(f'<i style="height:{h}%;--on:{color}"></i>')
    return "".join(out)


def _external_href(url: str) -> str:
    url = url.strip()
    if url and not re.match(r"^https?://", url):
        url = "https://" + url
    return url


def _display_phone(phone: str) -> str:
    """+351999123456 -> +351 999 123 456; anything else shows as typed."""
    digits = phone.strip().replace(" ", "")
    m = re.match(r"^(\+351)(\d{3})(\d{3})(\d{3})$", digits)
    if m:
        return " ".join(m.groups())
    return phone.strip()


def _display_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/")


PAGE_TEMPLATE = Template("""<!doctype html>
<html lang="$lang">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>$title</title>
<link rel="icon" href="data:image/svg+xml,$favicon">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&amp;family=Inter:wght@400;500;600&amp;display=swap">
<style>
:root{
  --bg:#0D1114; --surface:#1A1A18; --text:#F5F5F0; --body:#A3A39F; --muted:#6B6B68;
  --border:rgba(232,232,227,0.08); --teal:#00A79D; --blue:#0095DA;
  --grad:linear-gradient(90deg,#00A79D 0%,#0095DA 100%);
}
*{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--bg); color:var(--body);
  font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:1rem; line-height:1.65; min-height:100vh;
  display:flex; padding:2rem 1.25rem;
}
body::before{
  content:""; position:fixed; inset:0; pointer-events:none;
  background:radial-gradient(ellipse 90% 55% at 50% -12%, rgba(0,167,157,0.09), transparent 65%);
}
main{width:100%;max-width:480px;position:relative;text-align:center;margin:auto}
.logo svg{height:26px;width:auto;display:inline-block}
.eyebrow{
  margin-top:2.4rem; font-size:.72rem; font-weight:600; letter-spacing:.16em;
  text-transform:uppercase; color:var(--muted);
}
h1{
  font-family:'Libre Baskerville',Georgia,'Times New Roman',serif;
  font-weight:700; font-size:clamp(1.7rem,6.5vw,2.3rem); line-height:1.25;
  color:var(--text); margin-top:.45rem;
}
.biz{margin-top:.35rem;font-size:.95rem;color:var(--muted)}
.player{
  margin-top:2.2rem; background:var(--surface); border:1px solid var(--border);
  border-radius:4px; padding:1.25rem 1.25rem 1rem;
  display:flex; align-items:center; gap:1rem; text-align:left;
}
.pp{
  flex:0 0 56px; width:56px; height:56px; border-radius:50%; border:0;
  background:var(--grad); color:#fff; cursor:pointer;
  display:flex; align-items:center; justify-content:center;
  transition:transform .15s ease, opacity .15s ease;
}
.pp:hover{opacity:.88;transform:scale(1.04)}
.pp:active{transform:scale(.97)}
.pp svg{width:20px;height:20px;fill:#fff}
.pp .ic-pause{display:none}
.playing .pp .ic-play{display:none}
.playing .pp .ic-pause{display:block}
.meter{flex:1;min-width:0}
.wave{display:flex;align-items:center;gap:3px;height:52px;cursor:pointer}
.wave i{
  flex:1; min-width:2px; border-radius:2px;
  background:rgba(245,245,240,0.14); transition:background-color .2s ease;
}
.wave i.on{background:var(--on)}
.time{
  display:block; margin-top:.5rem; font-size:.78rem; color:var(--muted);
  font-variant-numeric:tabular-nums;
}
.sender{margin-top:1.9rem;font-size:.95rem;color:var(--body)}
.sender b{color:var(--text);font-weight:600}
.actions{margin-top:1.6rem;display:flex;flex-direction:column;gap:.7rem;align-items:center}
.btn{
  display:inline-flex; align-items:center; justify-content:center; gap:.5rem;
  font-weight:600; font-size:1rem; line-height:1; text-decoration:none;
  padding:.95rem 1.9rem; border-radius:4px; min-height:44px;
  transition:opacity .15s ease, transform .15s ease;
}
.btn-primary{background:var(--grad);color:#fff}
.btn-primary:hover{opacity:.88;transform:translateY(-1px)}
.contact{margin-top:1.3rem;font-size:.85rem}
.contact-line{display:flex;justify-content:center;flex-wrap:wrap;column-gap:.3rem;align-items:center}
.contact a{color:var(--body);text-decoration:none;padding:.65rem .4rem;display:inline-block}
.contact a:hover{color:var(--teal)}
.contact .dot{color:var(--muted)}
footer{margin-top:2.6rem;font-size:.78rem;color:var(--muted)}
a:focus-visible,button:focus-visible{outline:2px solid var(--teal);outline-offset:3px}
@media (prefers-reduced-motion: reduce){
  *{transition:none !important}
}
</style>
</head>
<body>
<main>
  <div class="logo">$logo_svg</div>
  <p class="eyebrow">$eyebrow</p>
  <h1>$name</h1>
  $biz_row
  <div class="player">
    <button class="pp" id="pp" aria-label="$play_label" data-play="$play_label" data-pause="$pause_label">
      <svg class="ic-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>
      <svg class="ic-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
    </button>
    <div class="meter">
      <div class="wave" id="wave">$bars</div>
      <span class="time" id="time">0:00 / 0:00</span>
    </div>
  </div>
  <p class="sender">$sender_line</p>
  <div class="actions">
    $cta_row
  </div>
  $contact_block
  <footer>$footer_line</footer>
</main>
<audio id="au" src="$audio_file" preload="metadata"></audio>
<script>
(function(){
  var au=document.getElementById('au'),pp=document.getElementById('pp'),
      wave=document.getElementById('wave'),t=document.getElementById('time'),
      bars=wave.querySelectorAll('i');
  function fmt(s){
    if(!isFinite(s)||s<0)s=0;
    var m=Math.floor(s/60),r=Math.floor(s%60);
    return m+':'+(r<10?'0':'')+r;
  }
  function paint(){
    var d=au.duration||0,c=au.currentTime||0,k=d?Math.floor(c/d*bars.length):0;
    for(var i=0;i<bars.length;i++)bars[i].classList.toggle('on',i<k);
    t.textContent=fmt(c)+' / '+fmt(d);
  }
  pp.addEventListener('click',function(){au.paused?au.play():au.pause();});
  au.addEventListener('play',function(){
    document.body.classList.add('playing');
    pp.setAttribute('aria-label',pp.getAttribute('data-pause'));
  });
  au.addEventListener('pause',function(){
    document.body.classList.remove('playing');
    pp.setAttribute('aria-label',pp.getAttribute('data-play'));
  });
  au.addEventListener('timeupdate',paint);
  au.addEventListener('loadedmetadata',paint);
  au.addEventListener('ended',function(){au.currentTime=0;paint();});
  wave.addEventListener('click',function(e){
    if(!au.duration)return;
    var r=wave.getBoundingClientRect();
    au.currentTime=au.duration*Math.min(1,Math.max(0,(e.clientX-r.left)/r.width));
    paint();
    if(au.paused)au.play();
  });
})();
</script>
</body>
</html>
""")


INDEX_TEMPLATE = Template("""<!doctype html>
<html lang="$lang">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>$title</title>
<link rel="icon" href="data:image/svg+xml,$favicon">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@700&amp;family=Inter:wght@400;500;600&amp;display=swap">
<style>
:root{
  --bg:#0D1114; --surface:#1A1A18; --text:#F5F5F0; --body:#A3A39F; --muted:#6B6B68;
  --border:rgba(232,232,227,0.08); --teal:#00A79D;
}
*{margin:0;padding:0;box-sizing:border-box}
body{
  background:var(--bg); color:var(--body);
  font-family:'Inter',system-ui,sans-serif; line-height:1.6; padding:3rem 1.25rem;
}
main{max-width:720px;margin:0 auto}
.logo svg{height:22px;width:auto}
h1{
  font-family:'Libre Baskerville',Georgia,serif; color:var(--text);
  font-size:1.6rem; margin-top:1.6rem;
}
.meta{font-size:.85rem;color:var(--muted);margin-top:.3rem}
ul{list-style:none;margin-top:2rem;display:flex;flex-direction:column;gap:.6rem}
li{
  background:var(--surface); border:1px solid var(--border); border-radius:4px;
  padding:.9rem 1.1rem; display:flex; flex-wrap:wrap; gap:.35rem 1rem; align-items:baseline;
}
li a{color:var(--teal);font-weight:600;text-decoration:none}
li a:hover{text-decoration:underline}
.who{color:var(--text)}
.excerpt{flex-basis:100%;font-size:.85rem;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
a:focus-visible{outline:2px solid var(--teal);outline-offset:3px}
</style>
</head>
<body>
<main>
  <div class="logo">$logo_svg</div>
  <h1>$job_name</h1>
  <p class="meta">$meta_line</p>
  <ul>
$rows
  </ul>
</main>
</body>
</html>
""")


def _render_page(item: dict, profile: dict, s: dict, lang: str, audio_file: str) -> str:
    lead = item["lead"]
    name = _lead_name(lead)
    business = (lead.get("business") or lead.get("company") or "").strip()
    business_name = (profile.get("business_name") or "").strip() or "Tembr"
    one_liner = (profile.get("one_liner") or "").strip()
    email = (profile.get("email") or "").strip()
    website = (profile.get("website") or "").strip()

    biz_row = ""
    if business and business.lower() != name.lower():
        biz_row = f'<p class="biz">{html.escape(business)}</p>'

    cta_row = ""
    if email:
        subject = quote(f"{s['subject']} · {business or name}")
        label = html.escape((profile.get("cta_label") or "").strip() or s["cta"])
        cta_row = (
            f'<a class="btn btn-primary" href="mailto:{quote(email, safe="@")}?subject={subject}">{label}</a>'
        )

    phone = (profile.get("phone") or "").strip()
    website2 = (profile.get("website2") or "").strip()
    line1 = []
    if phone:
        tel = re.sub(r"[^\d+]", "", phone)
        line1.append(f'<a href="tel:{html.escape(tel)}">{html.escape(_display_phone(phone))}</a>')
    if email:
        line1.append(f'<a href="mailto:{quote(email, safe="@")}">{html.escape(email)}</a>')
    line2 = []
    for site in (website, website2):
        if site:
            line2.append(
                f'<a href="{html.escape(_external_href(site))}" target="_blank" '
                f'rel="noopener">{html.escape(_display_url(site))}</a>'
            )
    sep = '<span class="dot">·</span>'
    contact_lines = [
        f'<div class="contact-line">{sep.join(links)}</div>'
        for links in (line1, line2)
        if links
    ]
    contact_block = (
        f'<div class="contact">{"".join(contact_lines)}</div>' if contact_lines else ""
    )

    sender_line = f"<b>{html.escape(business_name)}</b>"
    if one_liner:
        sender_line += f" · {html.escape(one_liner)}"

    return PAGE_TEMPLATE.substitute(
        lang=lang,
        title=html.escape(f"{s['eyebrow']} {name} · {business_name}"),
        favicon=quote(_load_brand("mark.svg")),
        logo_svg=_load_brand("logo.svg"),
        eyebrow=html.escape(s["eyebrow"]),
        name=html.escape(name),
        biz_row=biz_row,
        bars=_bars(item["id"]),
        play_label=html.escape(s["play"]),
        pause_label=html.escape(s["pause"]),
        sender_line=sender_line,
        cta_row=cta_row,
        contact_block=contact_block,
        footer_line=html.escape(f"{s['sent_by']} {business_name}"),
        audio_file=audio_file,
    )


def _render_index(job: dict, rows: list[dict], s: dict, lang: str) -> str:
    built = time.strftime("%Y-%m-%d %H:%M")
    items_html = []
    for r in rows:
        who = f'<span class="who">{html.escape(r["name"])}</span>'
        if r["business"]:
            who += f' <span>{html.escape(r["business"])}</span>'
        excerpt = html.escape(r["text"][:110])
        items_html.append(
            f'    <li><a href="{r["slug"]}/">{html.escape(s["open"])}</a> {who}'
            f'<span class="excerpt">{excerpt}</span></li>'
        )
    return INDEX_TEMPLATE.substitute(
        lang=lang,
        title=html.escape(job["name"]),
        favicon=quote(_load_brand("mark.svg")),
        logo_svg=_load_brand("logo.svg"),
        job_name=html.escape(job["name"]),
        meta_line=html.escape(f"{len(rows)} {s['pages']} · {s['built']} {built}"),
        rows="\n".join(items_html),
    )


def build_site(job: dict, items: list[dict], profile: dict) -> dict:
    lang = "pt" if str(job.get("language", "")).lower().startswith("pt") else "en"
    s = STRINGS[lang]
    site_dir = OUTREACH_DIR / job["id"] / "site"
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)

    warnings = []
    if not (profile.get("email") or "").strip():
        warnings.append(
            "The business profile has no email, so pages were built without the reply button. "
            "Add it in Settings and rebuild."
        )

    used: set[str] = set()
    rows: list[dict] = []
    pages = skipped = 0
    for item in items:
        if item["status"] != "done" or not item.get("output_path"):
            skipped += 1
            continue
        src = Path(item["output_path"])
        if not src.exists():
            skipped += 1
            continue
        slug = item_slug(item)
        if slug in used:
            slug = item["id"]
        used.add(slug)
        db.set_outreach_item_slug(item["id"], slug)

        page_dir = site_dir / slug
        page_dir.mkdir()
        audio_file = "message" + src.suffix
        shutil.copy2(src, page_dir / audio_file)
        (page_dir / "index.html").write_text(
            _render_page(item, profile, s, lang, audio_file), encoding="utf-8"
        )
        lead = item["lead"]
        rows.append(
            {
                "slug": slug,
                "name": _lead_name(lead),
                "business": (lead.get("business") or lead.get("company") or "").strip(),
                "text": item.get("text") or "",
            }
        )
        pages += 1

    (site_dir / "index.html").write_text(_render_index(job, rows, s, lang), encoding="utf-8")
    return {"pages": pages, "skipped": skipped, "warnings": warnings}

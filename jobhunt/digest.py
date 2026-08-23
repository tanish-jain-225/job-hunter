"""Build the daily HTML digest. Inline CSS + mobile media queries for responsive email clients down to 300px."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from .fetch import Job

BG = "#f8fafc"
CARD = "#ffffff"
LINE = "#e2e8f0"
TEXT = "#0f172a"
MUTED = "#64748b"
ACCENT = "#4f46e5"


def _badge(job: Job) -> str:
    s = job.score_100
    color = "#15803d" if s >= 90 else "#166534" if s >= 80 else "#b45309" if s >= 70 else "#475569"
    bg = "#dcfce7" if s >= 90 else "#f0fdf4" if s >= 80 else "#fef3c7" if s >= 70 else "#f1f5f9"
    badge_label = f"{job.queue_category} ({s}/100)"
    return (f'<span style="background:{bg};color:{color};font-weight:800;'
            f'padding:5px 12px;border-radius:999px;font-size:12.5px;border:1px solid {LINE};'
            f'display:inline-block;text-align:center;'
            f'word-break:break-word;overflow-wrap:anywhere;max-width:100%;box-sizing:border-box;">{badge_label}</span>')

def _job_type_badge(j: Job) -> str:
    hay = f"{j.title} {j.location}".lower()
    if any(h in hay for h in ("remote", "wfh", "work from home", "distributed")):
        return '<span style="background:#dbeafe;color:#1d4ed8;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;border:1px solid #bfdbfe;">🌐 Remote</span>'
    elif any(h in hay for h in ("hybrid", "flexible")):
        return '<span style="background:#fef3c7;color:#92400e;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;border:1px solid #fde68a;">🔀 Hybrid</span>'
    elif any(h in hay for h in ("intern", "internship", "trainee")):
        return '<span style="background:#f0fdf4;color:#166534;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;border:1px solid #bbf7d0;">🎓 Internship</span>'
    else:
        return '<span style="background:#f1f5f9;color:#475569;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;border:1px solid #e2e8f0;">🏢 On-Site</span>'

def _bullets(items: list[str]) -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin:0 0 6px 0;color:#334155;font-size:13.5px;line-height:1.5;'
        f'word-break:break-word;overflow-wrap:anywhere;">'
        f'{html.escape(str(i))}</li>' for i in items)
    return f'<ul style="margin:8px 0 0 0;padding-left:18px;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">{lis}</ul>'


def _section(label: str, body: str) -> str:
    if not body:
        return ""
    return (f'<div style="margin-top:14px;width:100%;box-sizing:border-box;display:block;clear:both;">'
            f'<div style="color:{MUTED};font-size:11px;letter-spacing:.09em;'
            f'text-transform:uppercase;font-weight:800;word-break:break-word;overflow-wrap:anywhere;">{label}</div>{body}</div>')


def _para(t: str) -> str:
    if not t:
        return ""
    return (f'<p style="margin:8px 0 0 0;color:#334155;font-size:13.5px;'
            f'line-height:1.6;word-break:break-word;overflow-wrap:anywhere;">{html.escape(t)}</p>')


def _card(j: Job) -> str:
    d = j.draft or {}
    meta = " · ".join(x for x in [j.company, j.location or "—", j.ats] if x)

    # Compute india_eligibility from draft or location data
    india_badge = d.get("india_eligibility")
    if not india_badge:
        location_lower = (j.location or "").lower()
        india_keywords = ["india", "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad",
                           "pune", "chennai", "noida", "gurugram", "gurgaon", "remote",
                           "work from home", "wfh", "anywhere"]
        if any(kw in location_lower for kw in india_keywords):
            india_badge = "🇮🇳 India-Based Role"
        elif not j.location or j.location.strip() == "":
            india_badge = "📍 Location TBD"
        else:
            india_badge = "🌐 Global / Check Location"

    salary_html = ""
    salary_val = d.get("salary_range_inr") or getattr(j, "salary", "")
    if salary_val:
        salary_html = f'<span style="background:#ecfdf5;color:#065f46;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;border:1px solid #a7f3d0;word-break:break-word;overflow-wrap:anywhere;display:inline-block;max-width:100%;box-sizing:border-box;">💰 {html.escape(str(salary_val))}</span>'

    # Display a concise Why It Fits summary
    fit_text = d.get("fit_summary") or j.reason or ""
    fit_html = _section("Why It Fits", _para(fit_text))

    return f"""
<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:18px 16px;margin-bottom:18px;box-shadow:0 2px 5px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;">
  <div class="card-header-flex" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;width:100%;box-sizing:border-box;margin-bottom:10px;">
    <div style="flex:1 1 200px;min-width:0;display:block;">
      <div style="font-size:16.5px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;overflow-wrap:anywhere;">{html.escape(j.title)}</div>
      <div style="color:{MUTED};font-size:12.5px;margin-top:4px;font-weight:500;word-break:break-word;overflow-wrap:anywhere;">{html.escape(meta)}</div>
    </div>
    <div class="card-badge-wrap" style="flex-shrink:0;display:inline-block;max-width:100%;">{_badge(j)}</div>
  </div>

  <div style="margin-top:10px;margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap;width:100%;box-sizing:border-box;">
    {_job_type_badge(j)}
    <span style="background:#eff6ff;color:#1d4ed8;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;border:1px solid #bfdbfe;word-break:break-word;overflow-wrap:anywhere;display:inline-block;max-width:100%;box-sizing:border-box;">{html.escape(india_badge)}</span>
    {salary_html}
  </div>

  {fit_html}

  <div class="card-footer-flex" style="margin-top:16px;padding-top:12px;border-top:1px solid {LINE};display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;width:100%;box-sizing:border-box;">
    <a href="{html.escape(j.url)}" target="_blank" rel="noopener noreferrer" class="btn-apply-email" style="display:inline-block;background:{ACCENT};
       color:#ffffff;font-weight:700;font-size:13px;text-decoration:none;
       padding:9px 16px;border-radius:8px;box-shadow:0 2px 4px rgba(79,70,229,0.25);word-break:break-word;overflow-wrap:anywhere;text-align:center;box-sizing:border-box;">Open Job Listing &amp; Apply →</a>
    <span style="color:{MUTED};font-size:11px;word-break:break-all;overflow-wrap:anywhere;text-align:right;">ID: {html.escape(j.job_id)}</span>
  </div>
</div>"""


def build(jobs: list[Job], scanned: int, candidates: int, stats: dict, profile: dict | None = None) -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    name = ""
    if profile and profile.get("name"):
        name = str(profile["name"]).strip()
    elif profile and profile.get("email"):
        username = str(profile["email"]).split("@")[0]
        name = " ".join(part.capitalize() for part in username.replace(".", " ").replace("_", " ").split())
    if not name:
        name = "Candidate"

    edu = str((profile or {}).get("education") or "").strip()
    cand_info = f"<b>{html.escape(name)}</b>"
    if edu:
        cand_info += f" ({html.escape(str(edu))})"

    subject = (f"{len(jobs)} Remote Role{'s' if len(jobs) != 1 else ''} Matched for {name} — {today}"
               if jobs else f"No new remote matches today — {today}")

    if jobs:
        body = "".join(_card(j) for j in jobs)
    else:
        body = (f'<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;'
                f'padding:20px 16px;color:{MUTED};font-size:13.5px;line-height:1.6;word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;">Scanned {scanned} postings across 40+ ATS boards, '
                f'0 candidates cleared the 70+ match bar today.</div>')

    html_doc = f"""<!doctype html>
<html lang="en" style="box-sizing:border-box;-webkit-text-size-adjust:100%;">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <base target="_blank">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ margin: 0; padding: 0; background-color: {BG}; -webkit-text-size-adjust: 100%; }}
    img, table {{ max-width: 100%; height: auto; }}
    @media only screen and (max-width: 480px) {{
      .digest-wrap {{ padding: 12px 6px !important; }}
      .digest-card {{ padding: 14px 10px !important; border-radius: 10px !important; margin-bottom: 12px !important; }}
      .card-header-flex {{ flex-direction: column !important; align-items: stretch !important; gap: 8px !important; }}
      .card-badge-wrap {{ align-self: flex-start !important; margin-top: 4px !important; }}
      .card-footer-flex {{ flex-direction: column !important; align-items: stretch !important; gap: 8px !important; }}
      .btn-apply-email {{ width: 100% !important; text-align: center !important; justify-content: center !important; }}
      .digest-title {{ font-size: 19px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:16px 8px;background:{BG};box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%;color:{TEXT};">
  <div class="digest-wrap" style="max-width:680px;width:100%;margin:0 auto;display:block;clear:both;box-sizing:border-box;">
    <div class="digest-title" style="color:{TEXT};font-size:22px;font-weight:800;letter-spacing:-0.02em;line-height:1.25;margin-bottom:6px;display:block;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">Job Hunter — Career Intelligence Briefing</div>
    <div style="color:{MUTED};font-size:12.5px;margin:0 0 20px 0;line-height:1.5;display:block;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">
      {today} · Candidate: {cand_info} · Scanned <b>{scanned}</b> postings · <b>{candidates}</b> passed filter · <b>{len(jobs)}</b> shortlisted<br>
      Tracker: {stats.get('tracked', 0)} total seen
    </div>
    {body}
    <div style="color:{MUTED};font-size:11px;line-height:1.6;margin-top:20px;border-top:1px solid {LINE};padding-top:12px;display:block;clear:both;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">
      Autonomous execution engine by Job Hunter. Application kits drafted from candidate profile.
    </div>
  </div>
</body>
</html>"""
    return subject, html_doc


def write(html_doc: str, path: str | Path = "out/digest.html") -> Path:
    from .store import get_writable_path
    target_path = get_writable_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(html_doc, encoding="utf-8")
    return target_path

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
WEBSITE_URL = "https://job-hunter-web-board.vercel.app"
LOGO_URL = f"{WEBSITE_URL}/logo.png"


def _badge(job: Job) -> str:
    s = job.score_100
    color = "#15803d" if s >= 90 else "#166534" if s >= 80 else "#b45309" if s >= 70 else "#475569"
    bg = "#dcfce7" if s >= 90 else "#f0fdf4" if s >= 80 else "#fef3c7" if s >= 70 else "#f1f5f9"
    badge_label = f"{job.queue_category} ({s}/100)"
    return (
        f'<span style="background:{bg};color:{color};font-weight:800;'
        f"padding:5px 12px;border-radius:999px;font-size:12.5px;border:1px solid {LINE};"
        f"display:inline-block;text-align:center;"
        f'word-break:break-word;overflow-wrap:anywhere;max-width:100%;box-sizing:border-box;">{badge_label}</span>'
    )


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
        f"{html.escape(str(i))}</li>"
        for i in items
    )
    return f'<ul style="margin:8px 0 0 0;padding-left:18px;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">{lis}</ul>'


def _section(label: str, body: str) -> str:
    if not body:
        return ""
    return (
        f'<div style="margin-top:14px;width:100%;box-sizing:border-box;display:block;clear:both;">'
        f'<div style="color:{MUTED};font-size:11px;letter-spacing:.09em;'
        f'text-transform:uppercase;font-weight:800;word-break:break-word;overflow-wrap:anywhere;">{label}</div>{body}</div>'
    )


def _para(t: str) -> str:
    if not t:
        return ""
    return (
        f'<p style="margin:8px 0 0 0;color:#334155;font-size:13.5px;'
        f'line-height:1.6;word-break:break-word;overflow-wrap:anywhere;">{html.escape(t)}</p>'
    )


def _card(j: Job) -> str:
    d = j.draft or {}
    meta = " · ".join(x for x in [j.company, j.location or "—", j.ats] if x)

    # Compute india_eligibility from draft or location data
    india_badge = d.get("india_eligibility")
    if not india_badge:
        location_lower = (j.location or "").lower()
        india_keywords = [
            "india",
            "bengaluru",
            "bangalore",
            "mumbai",
            "delhi",
            "hyderabad",
            "pune",
            "chennai",
            "noida",
            "gurugram",
            "gurgaon",
            "remote",
            "work from home",
            "wfh",
            "anywhere",
        ]
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
<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:18px 16px;margin-bottom:16px;box-shadow:0 1px 3px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;">
  <div class="card-header-flex" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;width:100%;box-sizing:border-box;margin-bottom:10px;">
    <div style="flex:1 1 180px;min-width:0;display:block;">
      <div style="font-size:16px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;overflow-wrap:anywhere;">{html.escape(j.title)}</div>
      <div style="color:{MUTED};font-size:12.5px;margin-top:4px;font-weight:500;word-break:break-word;overflow-wrap:anywhere;">{html.escape(meta)}</div>
    </div>
    <div class="card-badge-wrap" style="flex-shrink:0;display:inline-block;max-width:100%;box-sizing:border-box;">{_badge(j)}</div>
  </div>

  <div class="card-badges-flex" style="margin-top:10px;margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap;width:100%;box-sizing:border-box;">
    {_job_type_badge(j)}
    <span style="background:#eff6ff;color:#1d4ed8;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;border:1px solid #bfdbfe;word-break:break-word;overflow-wrap:anywhere;display:inline-block;max-width:100%;box-sizing:border-box;">{html.escape(india_badge)}</span>
    {salary_html}
  </div>

  {fit_html}

  <div class="card-footer-flex" style="margin-top:16px;padding-top:12px;border-top:1px solid {LINE};display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;width:100%;box-sizing:border-box;">
    <a href="{html.escape(j.url)}" target="_blank" rel="noopener noreferrer" class="btn-apply-email" style="display:inline-flex;align-items:center;justify-content:center;background:{ACCENT};
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

    target_titles = (profile or {}).get("target_keywords") or (profile or {}).get("target_titles") or []
    target_str = ", ".join(str(t) for t in target_titles[:3]) if target_titles else "Software Engineering"

    skills = (profile or {}).get("skills") or (profile or {}).get("core_skills") or []
    skills_str = ", ".join(str(s) for s in skills[:6]) if skills else "Core Stack"

    pref_locs = (profile or {}).get("preferred_locations") or []
    locs_str = ", ".join(str(l) for l in pref_locs) if pref_locs else "India / Remote / Global"

    if jobs:
        subject = f"{len(jobs)} Remote Role{'s' if len(jobs) != 1 else ''} Matched for {name} — {today}"
        body = "".join(_card(j) for j in jobs)
    else:
        subject = (
            f"No new remote matches today for {name} — {today}"
            if name != "Candidate"
            else f"No new remote matches today — {today}"
        )
        body = f"""
<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:22px 18px;box-shadow:0 1px 3px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;">
  <div class="empty-header-flex" style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;width:100%;box-sizing:border-box;">
    <div style="background:#eff6ff;line-height:1;padding:6px;border-radius:10px;border:1px solid #bfdbfe;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;">
      <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;text-decoration:none;">
        <img src="{LOGO_URL}" alt="Job Hunter" width="32" height="32" class="empty-logo-img" style="display:block;width:32px;height:32px;border-radius:6px;flex-shrink:0;min-width:32px;" onerror="this.src='/logo.png'">
      </a>
    </div>
    <div style="flex:1 1 180px;min-width:0;">
      <div class="empty-title" style="font-size:17px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;overflow-wrap:anywhere;">Daily Radar Scan Completed</div>
      <div class="empty-desc" style="color:{MUTED};font-size:12.5px;margin-top:2px;word-break:break-word;overflow-wrap:anywhere;">No new high-match postings found (0 candidates cleared the match bar today)</div>
    </div>
  </div>

  <p style="color:#334155;font-size:13.5px;line-height:1.6;margin-bottom:14px;word-break:break-word;overflow-wrap:anywhere;">
    Our autonomous crawler scanned <b>{scanned} postings</b> across <b>100+ verified ATS company boards</b> (Greenhouse, Lever, Ashby, Workable, SmartRecruiters).
  </p>

  <div style="background:#f8fafc;border:1px solid {LINE};border-radius:8px;padding:12px 14px;margin-bottom:16px;box-sizing:border-box;width:100%;">
    <div style="color:{MUTED};font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Active Criteria Evaluated</div>
    <div style="font-size:12.5px;color:#334155;line-height:1.5;word-break:break-word;overflow-wrap:anywhere;">
      • <b>Target Roles:</b> {html.escape(target_str)}<br>
      • <b>Locations:</b> {html.escape(locs_str)}<br>
      • <b>Key Skills:</b> {html.escape(skills_str)}
    </div>
  </div>

  <div style="color:#475569;font-size:13px;line-height:1.5;word-break:break-word;overflow-wrap:anywhere;">
    💡 <b>Radar Status: Active &amp; Monitoring.</b> You will be immediately alerted as soon as new matching opportunities are published by target companies.
  </div>
</div>"""

    html_doc = f"""<!doctype html>
<html lang="en" style="box-sizing:border-box;-webkit-text-size-adjust:100%;">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <base target="_blank">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; min-width: 0; }}
    .digest-logo-img, .empty-logo-img, .digest-footer-logo {{ flex-shrink: 0 !important; min-width: fit-content; }}
    body {{ margin: 0; padding: 0; background-color: {BG}; -webkit-text-size-adjust: 100%; color: {TEXT}; }}
    img {{ max-width: 100%; height: auto; }}
    table {{ max-width: 100%; }}
    @media only screen and (max-width: 480px) {{
      .digest-wrap {{ padding: 10px 4px !important; }}
      .digest-card {{ padding: 14px 10px !important; border-radius: 10px !important; margin-bottom: 12px !important; }}
      .digest-header-flex {{ gap: 8px !important; }}
      .card-header-flex {{ flex-direction: column !important; align-items: stretch !important; gap: 8px !important; }}
      .card-badge-wrap {{ align-self: flex-start !important; margin-top: 4px !important; }}
      .card-footer-flex {{ flex-direction: column !important; align-items: stretch !important; gap: 8px !important; }}
      .btn-apply-email {{ width: 100% !important; text-align: center !important; justify-content: center !important; }}
      .digest-title {{ font-size: 18px !important; }}
      .digest-footer {{ margin-top: 18px !important; padding-top: 12px !important; }}
    }}
    @media only screen and (max-width: 340px) {{
      .digest-wrap {{ padding: 6px 2px !important; }}
      .digest-card {{ padding: 10px 6px !important; border-radius: 8px !important; margin-bottom: 10px !important; }}
      .digest-header-flex {{ gap: 6px !important; }}
      .digest-logo-img {{ width: 30px !important; height: 30px !important; border-radius: 7px !important; }}
      .digest-title {{ font-size: 15px !important; line-height: 1.25 !important; }}
      .digest-meta-line {{ font-size: 11px !important; line-height: 1.4 !important; }}
      .card-header-flex {{ gap: 6px !important; }}
      .card-badges-flex {{ gap: 4px !important; }}
      .btn-apply-email {{ font-size: 11px !important; padding: 7px 10px !important; border-radius: 6px !important; }}
      .empty-header-flex {{ gap: 8px !important; }}
      .empty-logo-img {{ width: 24px !important; height: 24px !important; }}
      .empty-title {{ font-size: 14px !important; }}
      .empty-desc {{ font-size: 11px !important; }}
      .digest-footer {{ font-size: 10px !important; margin-top: 14px !important; padding-top: 10px !important; gap: 6px !important; }}
      .digest-footer-logo {{ width: 16px !important; height: 16px !important; }}
      .digest-footer-text {{ font-size: 10px !important; }}
      .digest-footer-source-row {{ font-size: 9.5px !important; }}
    }}
    @media only screen and (max-width: 300px) {{
      .digest-wrap {{ padding: 4px 1px !important; }}
      .digest-card {{ padding: 8px 4px !important; border-radius: 6px !important; }}
      .digest-title {{ font-size: 13.5px !important; }}
      .btn-apply-email {{ font-size: 10.5px !important; padding: 6px 8px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:16px 8px;background:{BG};box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%;color:{TEXT};">
  <div class="digest-wrap" style="max-width:680px;width:100%;margin:0 auto;display:block;clear:both;box-sizing:border-box;">
    <div class="digest-header-flex" style="display:flex;align-items:center;gap:12px;margin-bottom:12px;width:100%;box-sizing:border-box;flex-wrap:wrap;">
      <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;text-decoration:none;flex-shrink:0;">
        <img src="{LOGO_URL}" alt="Job Hunter Logo" width="40" height="40" class="digest-logo-img" style="display:block;width:40px;height:40px;border-radius:10px;border:1px solid {LINE};object-fit:contain;flex-shrink:0;min-width:40px;" onerror="this.src='/logo.png'">
      </a>
      <div class="digest-title" style="flex:1 1 200px;min-width:0;color:{TEXT};font-size:22px;font-weight:800;letter-spacing:-0.02em;line-height:1.25;margin:0;word-break:break-word;overflow-wrap:anywhere;">Job Hunter — Career Intelligence Briefing</div>
    </div>
    <div class="digest-meta-line" style="color:{MUTED};font-size:12.5px;margin:0 0 18px 0;line-height:1.5;display:block;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">
      {today} · Candidate: {cand_info} · Scanned <b>{scanned}</b> postings · <b>{candidates}</b> passed filter · <b>{len(jobs)}</b> shortlisted<br>
      Tracker: {stats.get("tracked", 0)} total seen
    </div>
    {body}
    <div class="digest-footer" style="color:{MUTED};font-size:11.5px;line-height:1.6;margin-top:24px;border-top:1px solid {LINE};padding-top:14px;display:flex;flex-direction:column;gap:8px;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;">
      <div class="digest-footer-brand-row" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;width:100%;box-sizing:border-box;">
        <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:inline-flex;align-items:center;flex-shrink:0;">
          <img src="{LOGO_URL}" alt="Job Hunter" width="20" height="20" class="digest-footer-logo" style="display:block;width:20px;height:20px;border-radius:4px;border:1px solid {LINE};flex-shrink:0;min-width:20px;" onerror="this.src='/logo.png'">
        </a>
        <span class="digest-footer-text" style="color:{MUTED};font-size:11.5px;line-height:1.5;flex:1 1 180px;min-width:0;word-break:break-word;overflow-wrap:anywhere;">
          Autonomous execution engine by <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="color:{ACCENT};font-weight:700;text-decoration:none;">Job Hunter</a>. Application kits drafted from candidate profile.
        </span>
      </div>
      <div class="digest-footer-source-row" style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;font-size:11px;color:#94a3b8;width:100%;box-sizing:border-box;word-break:break-all;">
        <span>Source:</span>
        <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="color:{ACCENT};text-decoration:underline;font-weight:600;word-break:break-all;">{WEBSITE_URL}</a>
      </div>
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

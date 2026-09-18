"""Build the daily HTML digest. Bulletproof HTML email standards for all clients (Gmail Mobile, iOS, Outlook, Web)."""

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
        f"display:inline-block;vertical-align:middle;text-align:center;line-height:1.2;"
        f'word-break:break-word;overflow-wrap:anywhere;max-width:100%;box-sizing:border-box;margin:0 0 6px 0;">{badge_label}</span>'
    )


def _job_type_badge(j: Job) -> str:
    hay = f"{j.title} {j.location}".lower()
    common_style = "display:inline-block;vertical-align:middle;font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;line-height:1.2;box-sizing:border-box;margin:0 6px 6px 0;"
    if any(h in hay for h in ("remote", "wfh", "work from home", "distributed")):
        return f'<span style="{common_style}background:#dbeafe;color:#1d4ed8;border:1px solid #bfdbfe;">Remote</span>'
    elif any(h in hay for h in ("hybrid", "flexible")):
        return f'<span style="{common_style}background:#fef3c7;color:#92400e;border:1px solid #fde68a;">Hybrid</span>'
    elif any(h in hay for h in ("intern", "internship", "trainee")):
        return f'<span style="{common_style}background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;">Internship</span>'
    else:
        return f'<span style="{common_style}background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;">On-Site</span>'


def _bullets(items: list[str]) -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin:0 0 5px 0;padding:0;color:#334155;font-size:13px;line-height:1.5;'
        f'word-break:break-word;overflow-wrap:anywhere;">'
        f"{html.escape(str(i))}</li>"
        for i in items
    )
    return f'<ul style="margin:0 0 8px 0;padding-left:18px;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;display:block;">{lis}</ul>'


def _section(label: str, body: str) -> str:
    if not body:
        return ""
    return (
        f'<div style="width:100%;box-sizing:border-box;display:block;margin:0 0 14px 0;">'
        f'<div style="color:{MUTED};font-size:11px;letter-spacing:.09em;'
        f'text-transform:uppercase;font-weight:800;word-break:break-word;overflow-wrap:anywhere;margin:0 0 6px 0;display:block;">{label}</div>{body}</div>'
    )


def _para(t: str) -> str:
    if not t:
        return ""
    return (
        f'<p style="margin:0 0 6px 0;color:#334155;font-size:13.5px;'
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
            india_badge = "India-Based Role"
        elif not j.location or j.location.strip() == "":
            india_badge = "Location TBD"
        else:
            india_badge = "Global / Check Location"

    project_badge = ""
    best_project = d.get("best_project")
    if best_project:
        project_badge = f'<span style="background:#fdf2f8;color:#9d174d;font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:6px;border:1px solid #fbcfe8;display:inline-block;vertical-align:middle;line-height:1.2;word-break:break-word;overflow-wrap:anywhere;max-width:100%;box-sizing:border-box;margin:0 6px 6px 0;">Project: {html.escape(str(best_project))}</span>'

    salary_html = ""
    salary_val = d.get("salary_range_inr") or getattr(j, "salary", "")
    if salary_val:
        salary_html = f'<span style="background:#ecfdf5;color:#065f46;font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:6px;border:1px solid #a7f3d0;display:inline-block;vertical-align:middle;line-height:1.2;word-break:break-word;overflow-wrap:anywhere;max-width:100%;box-sizing:border-box;margin:0 6px 6px 0;">{html.escape(str(salary_val))}</span>'

    # Display concise sections
    fit_text = d.get("fit_summary") or j.reason or ""
    fit_html = _section("Why It Fits", _para(fit_text))

    bullets_html = _section("Tailored Highlights", _bullets(d.get("tailored_bullets", [])))
    skills_html = _section("Key Matching Skills", _bullets(d.get("matching_skills", [])))
    gaps_html = _section("Gaps & Hard Requirements", _bullets(d.get("gaps", [])))

    outreach_html = ""
    if d.get("cold_outreach"):
        outreach_html = _section(
            "Direct Outreach Note",
            f'<div style="background:#f8fafc;border:1px solid {LINE};border-radius:8px;padding:12px 14px;color:#1e293b;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;margin:0 0 4px 0;">{html.escape(str(d["cold_outreach"]))}</div>',
        )

    cover_html = ""
    if d.get("cover_note"):
        cover_html = _section(
            "Cover Note (Edit Before Sending)",
            f'<div style="background:#f8fafc;border:1px solid {LINE};border-radius:8px;padding:12px 14px;color:#1e293b;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;margin:0 0 4px 0;">{html.escape(str(d["cover_note"]))}</div>',
        )

    questions_html = _section("Technical Questions to Ask", _bullets(d.get("questions_to_ask", [])))

    return f"""
<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:20px;margin-bottom:18px;box-shadow:0 1px 3px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;">
  <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;margin:0 0 10px 0;">
    <tr>
      <td align="left" valign="top" style="vertical-align:top;text-align:left;padding:0 12px 0 0;">
        <div style="font-size:16px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;overflow-wrap:anywhere;margin:0 0 4px 0;">{html.escape(j.title)}</div>
        <div style="color:{MUTED};font-size:12.5px;font-weight:500;word-break:break-word;overflow-wrap:anywhere;">{html.escape(meta)}</div>
      </td>
      <td align="right" valign="top" style="vertical-align:top;text-align:right;white-space:nowrap;width:1%;">
        <div class="card-badge-wrap" style="display:inline-block;vertical-align:top;box-sizing:border-box;">{_badge(j)}</div>
      </td>
    </tr>
  </table>

  <div class="card-badges-wrap" style="display:block;width:100%;box-sizing:border-box;margin:0 0 10px 0;">
    {_job_type_badge(j)}
    <span style="background:#eff6ff;color:#1d4ed8;font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:6px;border:1px solid #bfdbfe;display:inline-block;vertical-align:middle;line-height:1.2;word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;margin:0 6px 6px 0;">{html.escape(india_badge)}</span>
    {project_badge}
    {salary_html}
  </div>

  {fit_html}
  {bullets_html}
  {skills_html}
  {gaps_html}
  {outreach_html}
  {cover_html}
  {questions_html}

  <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;margin-top:14px;padding-top:14px;border-top:1px solid {LINE};">
    <tr>
      <td align="left" valign="middle" class="card-footer-col" style="vertical-align:middle;text-align:left;">
        <a href="{html.escape(j.url)}" target="_blank" rel="noopener noreferrer" class="btn-apply-email" style="display:inline-block;vertical-align:middle;background:{ACCENT};
           color:#ffffff;font-weight:700;font-size:13px;text-decoration:none;
           padding:10px 20px;border-radius:8px;line-height:1.2;box-shadow:0 2px 4px rgba(79,70,229,0.25);word-break:break-word;overflow-wrap:anywhere;text-align:center;box-sizing:border-box;mso-padding-alt:0;">Open Job Listing &amp; Apply →</a>
      </td>
      <td align="right" valign="middle" class="card-footer-col" style="vertical-align:middle;text-align:right;white-space:nowrap;padding-left:12px;">
        <span style="color:{MUTED};font-size:11px;word-break:break-all;overflow-wrap:anywhere;">ID: {html.escape(j.job_id)}</span>
      </td>
    </tr>
  </table>
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
<div class="digest-card" style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:24px 20px;box-shadow:0 1px 3px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box;width:100%;display:block;clear:both;margin:0 0 18px 0;">
  <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;margin:0 0 14px 0;">
    <tr>
      <td valign="top" style="width:36px;vertical-align:top;padding:0 12px 0 0;">
        <div class="empty-logo-frame" style="background:#eff6ff;line-height:1;padding:6px;border-radius:10px;border:1px solid #bfdbfe;display:block;">
          <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="display:block;text-decoration:none;">
            <img src="{LOGO_URL}" alt="Job Hunter" width="32" height="32" border="0" class="empty-logo-img" style="display:block;width:32px;height:32px;aspect-ratio:1/1;object-fit:contain;border-radius:6px;outline:none;border:none;">
          </a>
        </div>
      </td>
      <td valign="top" style="vertical-align:top;text-align:left;">
        <div class="empty-title" style="font-size:17px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;overflow-wrap:anywhere;margin:0 0 4px 0;">Daily Radar Scan Completed</div>
        <div class="empty-desc" style="color:{MUTED};font-size:12.5px;line-height:1.4;word-break:break-word;overflow-wrap:anywhere;">No new high-match postings found (0 candidates cleared the match bar today)</div>
      </td>
    </tr>
  </table>

  <p style="color:#334155;font-size:13.5px;line-height:1.6;margin:0 0 14px 0;word-break:break-word;overflow-wrap:anywhere;">
    Our autonomous crawler scanned <b>{scanned} postings</b> across <b>88+ curated ATS company boards</b> (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint).
  </p>

  <div style="background:#f8fafc;border:1px solid {LINE};border-radius:8px;padding:14px 16px;box-sizing:border-box;width:100%;display:block;margin:0 0 14px 0;">
    <div style="color:{MUTED};font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 6px 0;display:block;">Active Criteria Evaluated</div>
    <div style="font-size:12.5px;color:#334155;line-height:1.6;word-break:break-word;overflow-wrap:anywhere;">
      • <b>Target Roles:</b> {html.escape(target_str)}<br>
      • <b>Locations:</b> {html.escape(locs_str)}<br>
      • <b>Key Skills:</b> {html.escape(skills_str)}
    </div>
  </div>

  <div style="color:#475569;font-size:13px;line-height:1.6;margin:0;word-break:break-word;overflow-wrap:anywhere;">
    <b>Radar Status: Active &amp; Monitoring.</b> You will be immediately alerted as soon as new matching opportunities are published by target companies.
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
    body {{ margin: 0; padding: 0; background-color: {BG}; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; color: {TEXT}; font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
    table, td {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ max-width: 100%; height: auto; border: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }}
    .digest-logo-img, .empty-logo-img, .digest-footer-logo {{ aspect-ratio: 1 / 1 !important; object-fit: contain !important; }}
    @media only screen and (max-width: 480px) {{
      .digest-wrap {{ padding: 12px 8px !important; }}
      .digest-card {{ padding: 16px 14px !important; border-radius: 10px !important; margin-bottom: 14px !important; }}
      .digest-title {{ font-size: 18px !important; }}
      .meta-table-col {{ display: block !important; width: 100% !important; text-align: left !important; padding: 2px 0 !important; }}
      .card-footer-col {{ display: block !important; width: 100% !important; text-align: left !important; padding: 4px 0 !important; }}
      .btn-apply-email {{ width: 100% !important; text-align: center !important; display: block !important; box-sizing: border-box !important; margin-bottom: 8px !important; }}
      .digest-footer {{ margin-top: 16px !important; padding-top: 14px !important; }}
    }}
    @media only screen and (max-width: 340px) {{
      .digest-wrap {{ padding: 8px 4px !important; }}
      .digest-card {{ padding: 12px 10px !important; border-radius: 8px !important; margin-bottom: 10px !important; }}
      .digest-title {{ font-size: 15px !important; }}
      .digest-meta-line {{ font-size: 11px !important; padding: 8px 10px !important; }}
      .empty-title {{ font-size: 14px !important; }}
      .empty-desc {{ font-size: 11px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:16px 8px;background:{BG};box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-text-size-adjust:100%;color:{TEXT};">
  <!--[if (gte mso 9)|(IE)]>
  <table align="center" border="0" cellpadding="0" cellspacing="0" width="680" style="width:680px;">
  <tr>
  <td align="left" valign="top">
  <![endif]-->
  <div class="digest-wrap" style="max-width:680px;width:100%;margin:0 auto;display:block;clear:both;box-sizing:border-box;">

    <!-- HEADER -->
    <div class="digest-header" style="display:block;width:100%;margin:0 0 16px 0;box-sizing:border-box;">
      <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;">
        <tr>
          <td valign="middle" style="width:40px;vertical-align:middle;padding:0 12px 0 0;">
            <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:block;">
              <img src="{LOGO_URL}" alt="Job Hunter Logo" width="40" height="40" border="0" class="digest-logo-img" style="display:block;width:40px;height:40px;aspect-ratio:1/1;object-fit:contain;border-radius:10px;border:1px solid {LINE};outline:none;text-decoration:none;">
            </a>
          </td>
          <td valign="middle" style="vertical-align:middle;text-align:left;">
            <div class="digest-title" style="color:{TEXT};font-size:22px;font-weight:800;letter-spacing:-0.02em;line-height:1.25;margin:0;word-break:break-word;overflow-wrap:anywhere;">Job Hunter — Career Intelligence Briefing</div>
          </td>
        </tr>
      </table>
    </div>

    <!-- META SUMMARY BAR -->
    <div class="digest-meta-line" style="color:{MUTED};font-size:12.5px;line-height:1.6;display:block;background:#ffffff;border:1px solid {LINE};border-radius:10px;padding:12px 16px;box-shadow:0 1px 2px rgba(15,23,42,0.04);width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;margin:0 0 16px 0;">
      <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;margin:0 0 4px 0;">
        <tr>
          <td align="left" valign="top" class="meta-table-col" style="vertical-align:top;font-size:12.5px;color:{MUTED};line-height:1.5;">
            {today} · Candidate: {cand_info}
          </td>
          <td align="right" valign="top" class="meta-table-col" style="vertical-align:top;font-size:12.5px;color:{MUTED};line-height:1.5;text-align:right;white-space:nowrap;padding-left:8px;">
            Tracker: <b>{stats.get('tracked', 0)}</b> total seen
          </td>
        </tr>
      </table>
      <div style="font-size:12px;color:{MUTED};line-height:1.5;display:block;">
        <span>Scanned <b>{scanned}</b> postings</span> ·
        <span><b>{candidates}</b> passed filter</span> ·
        <span style="color:#166534;font-weight:700;"><b>{len(jobs)}</b> shortlisted</span>
      </div>
    </div>

    <!-- CARDS / BODY -->
    {body}

    <!-- FOOTER -->
    <div class="digest-footer" style="color:{MUTED};font-size:11.5px;line-height:1.6;margin-top:16px;border-top:1px solid {LINE};padding-top:16px;display:block;width:100%;box-sizing:border-box;word-break:break-word;overflow-wrap:anywhere;clear:both;">
      <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="border-collapse:collapse;width:100%;margin:0 0 6px 0;">
        <tr>
          <td valign="top" style="width:20px;vertical-align:top;padding:2px 8px 0 0;">
            <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;display:block;">
              <img src="{LOGO_URL}" alt="Job Hunter" width="20" height="20" border="0" class="digest-footer-logo" style="display:block;width:20px;height:20px;aspect-ratio:1/1;object-fit:contain;border-radius:4px;border:1px solid {LINE};outline:none;text-decoration:none;">
            </a>
          </td>
          <td valign="top" style="vertical-align:top;text-align:left;">
            <span class="digest-footer-text" style="color:{MUTED};font-size:11.5px;line-height:1.5;display:block;word-break:break-word;overflow-wrap:anywhere;">
              Autonomous execution engine by <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="color:{ACCENT};font-weight:700;text-decoration:none;">Job Hunter</a>. Application kits drafted from candidate profile.
            </span>
          </td>
        </tr>
      </table>
      <div class="digest-footer-source-row" style="font-size:11px;color:#94a3b8;width:100%;box-sizing:border-box;word-break:break-all;margin-top:4px;display:block;">
        <span style="margin-right:2px;">Source:</span>
        <a href="{WEBSITE_URL}" target="_blank" rel="noopener noreferrer" style="color:{ACCENT};text-decoration:underline;font-weight:600;word-break:break-all;">{WEBSITE_URL}</a>
      </div>
    </div>

  </div>
  <!--[if (gte mso 9)|(IE)]>
  </td>
  </tr>
  </table>
  <![endif]-->
</body>
</html>"""
    return subject, html_doc


def write(html_doc: str, path: str | Path = "out/digest.html") -> Path:
    from .store import get_writable_path

    target_path = get_writable_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(html_doc, encoding="utf-8")
    return target_path

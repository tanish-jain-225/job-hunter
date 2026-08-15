"""Build the daily HTML digest. Inline CSS only — Gmail strips <style> blocks."""
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
            f'padding:6px 12px;border-radius:999px;font-size:13px;border:1px solid {LINE};">{badge_label}</span>')


def _bullets(items: list[str]) -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin:0 0 6px 0;color:#334155;font-size:14px;line-height:1.5;">'
        f'{html.escape(str(i))}</li>' for i in items)
    return f'<ul style="margin:8px 0 0 0;padding-left:18px;">{lis}</ul>'


def _section(label: str, body: str) -> str:
    if not body:
        return ""
    return (f'<div style="margin-top:14px;">'
            f'<div style="color:{MUTED};font-size:11px;letter-spacing:.09em;'
            f'text-transform:uppercase;font-weight:800;">{label}</div>{body}</div>')


def _para(t: str) -> str:
    if not t:
        return ""
    return (f'<p style="margin:8px 0 0 0;color:#334155;font-size:14px;'
            f'line-height:1.6;">{html.escape(t)}</p>')


def _card(j: Job) -> str:
    d = j.draft or {}
    meta = " · ".join(x for x in [j.company, j.location or "—", j.ats] if x)

    india_badge = d.get("india_eligibility", "Verified India-Friendly")
    best_project = d.get("best_project", "Edvanta")
    cold_outreach = d.get("cold_outreach", "")
    cover = d.get("cover_note", "")

    outreach_html = ""
    if cold_outreach:
        outreach_html = _section("⚡ Cold Outreach (<80 words — copy & send)",
            f'<div style="margin-top:8px;padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;'
            f'border-radius:8px;color:#166534;font-size:13px;line-height:1.6;font-family:monospace;white-space:pre-wrap;">{html.escape(cold_outreach)}</div>')

    cover_html = ""
    if cover:
        cover_html = _section("📝 Cover Note (Edit & Submit)",
            f'<div style="margin-top:8px;padding:12px;background:#f1f5f9;'
            f'border:1px solid {LINE};border-radius:8px;color:#1e293b;font-size:14px;'
            f'line-height:1.6;white-space:pre-wrap;">{html.escape(cover)}</div>')

    return f"""
<div style="background:{CARD};border:1px solid {LINE};border-radius:12px;padding:18px 16px;margin-bottom:18px;box-shadow:0 2px 5px rgba(15,23,42,0.06);word-break:break-word;overflow-wrap:break-word;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;">
    <div style="flex:1 1 200px;min-width:0;">
      <div style="font-size:17px;font-weight:800;color:{TEXT};line-height:1.3;word-break:break-word;">{html.escape(j.title)}</div>
      <div style="color:{MUTED};font-size:12.5px;margin-top:4px;font-weight:500;word-break:break-word;">{html.escape(meta)}</div>
    </div>
    <div style="flex-shrink:0;">{_badge(j)}</div>
  </div>

  <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
    <span style="background:#eff6ff;color:#1d4ed8;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;border:1px solid #bfdbfe;">🇮🇳 {html.escape(india_badge)}</span>
    <span style="background:#fef2f2;color:#b91c1c;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;border:1px solid #fecaca;">🚀 Project: {html.escape(best_project)}</span>
  </div>

  {_para(j.reason or "")}
  {_section("🎯 Why it fits", _para(d.get("fit_summary", "")))}
  {_section("📄 Resume bullets (dynamically tailored from resume.pdf)", _bullets(d.get("tailored_bullets", [])))}
  {_section("💡 Key Matching Skills", _bullets(d.get("matching_skills", [])))}
  {_section("⚠️ Gaps / Hard Requirements", _bullets(d.get("gaps", [])))}
  {outreach_html}
  {cover_html}
  {_section("❓ Technical Questions to Ask", _bullets(d.get("questions_to_ask", [])))}

  <div style="margin-top:16px;padding-top:12px;border-top:1px solid {LINE};display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
    <a href="{html.escape(j.url)}" style="display:inline-block;background:{ACCENT};
       color:#ffffff;font-weight:700;font-size:13.5px;text-decoration:none;
       padding:9px 16px;border-radius:8px;box-shadow:0 2px 4px rgba(79,70,229,0.25);word-break:break-word;">Open Job Listing &amp; Apply →</a>
    <span style="color:{MUTED};font-size:11px;word-break:break-all;">ID: {html.escape(j.job_id)}</span>
  </div>
</div>"""


def build(jobs: list[Job], scanned: int, candidates: int, stats: dict) -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    subject = (f"{len(jobs)} Remote Role{'s' if len(jobs) != 1 else ''} Matched for Tanish — {today}"
               if jobs else f"No new remote matches today — {today}")

    if jobs:
        body = "".join(_card(j) for j in jobs)
    else:
        body = (f'<div style="background:{CARD};border:1px solid {LINE};border-radius:12px;'
                f'padding:20px 16px;color:{MUTED};font-size:13.5px;word-break:break-word;">Scanned {scanned} postings across 40+ ATS boards, '
                f'0 candidates cleared the 70+ match bar today.</div>')

    html_doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head><body style="margin:0;padding:16px 12px;background:{BG};
box-sizing:border-box;word-break:break-word;overflow-wrap:break-word;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,sans-serif;">
<div style="max-width:680px;width:100%;margin:0 auto;box-sizing:border-box;">
  <div style="color:{TEXT};font-size:22px;font-weight:800;letter-spacing:-0.02em;line-height:1.2;">🏹 Job Hunter — Remote Briefing</div>
  <div style="color:{MUTED};font-size:12.5px;margin:6px 0 20px 0;line-height:1.5;word-break:break-word;">
    {today} · Candidate: <b>Tanish Sanghvi</b> (VESIT 2027) · Scanned <b>{scanned}</b> postings · <b>{candidates}</b> passed title/location filter · <b>{len(jobs)}</b> shortlisted<br>
    Tracker: {stats.get('tracked', 0)} total seen
  </div>
  {body}
  <div style="color:{MUTED};font-size:11px;line-height:1.6;margin-top:20px;
       border-top:1px solid {LINE};padding-top:12px;word-break:break-word;">
    Autonomous execution engine by Job Hunter. Application kits drafted from master resume.pdf.
  </div>
</div></body></html>"""
    return subject, html_doc
    return subject, html_doc


def write(html_doc: str, path: str | Path = "out/digest.html") -> Path:
    from .store import get_writable_path
    target_path = get_writable_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(html_doc, encoding="utf-8")
    return target_path



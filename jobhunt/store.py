"""seen.json doubles as the dedupe index AND the application tracker.

Equipped with persistent Supabase PostgreSQL memory synchronization
keyed on the user's authenticated email.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import urllib.parse

import threading
from .fetch import Job
from .memory import SupabaseMemory

_CSV_EXPORT_LOCK = threading.Lock()


def sanitize_job_url(
    url: str | None,
    ats: str = "",
    job_id: str = "",
    company: str = "",
    title: str = "",
) -> str:
    """Ensure every job has a valid, working HTTP/HTTPS apply URL.

    - If the URL is already a valid http/https link, preserves it.
    - If the URL is a domain without scheme (e.g. 'stripe.com/jobs'), prepends 'https://'.
    - If the URL is empty, '#', or broken, automatically constructs the canonical ATS apply URL.
    - If custom or unknown ATS, constructs a direct search/careers URL.
    """
    clean = (url or "").strip()
    if clean and clean != "#":
        if clean.startswith(("http://", "https://")):
            return clean
        if "." in clean and not clean.startswith(("/", "#", "javascript:")):
            return f"https://{clean}"

    effective_id = job_id or ""
    if ":" in effective_id:
        parts = effective_id.split(":", 2)
        ats_name = (ats or parts[0]).lower()
        slug = parts[1] if len(parts) > 1 else ""
        raw_id = parts[2] if len(parts) > 2 else ""

        if ats_name == "greenhouse" and slug and raw_id:
            return f"https://boards.greenhouse.io/{slug}/jobs/{raw_id}"
        elif ats_name == "lever" and slug and raw_id:
            return f"https://jobs.lever.co/{slug}/{raw_id}"
        elif ats_name == "ashby" and slug and raw_id:
            return f"https://jobs.ashbyhq.com/{slug}/{raw_id}"
        elif ats_name == "workable" and slug and raw_id:
            return f"https://apply.workable.com/{slug}/j/{raw_id}/"
        elif ats_name == "smartrecruiters" and slug and raw_id:
            return f"https://jobs.smartrecruiters.com/{slug}/{raw_id}"
        elif ats_name == "bamboohr" and slug and raw_id:
            return f"https://{slug}.bamboohr.com/careers/{raw_id}"
        elif ats_name == "recruitee" and slug and raw_id:
            return f"https://{slug}.recruitee.com/o/{raw_id}"
        elif ats_name in ("breezy", "breezyhr") and slug and raw_id:
            return f"https://{slug}.breezy.hr/p/{raw_id}"
        elif ats_name == "pinpoint" and slug and raw_id:
            return f"https://{slug}.pinpoint.work/en/postings/{raw_id}"

    query = f"{company} {title}".strip()
    if not query:
        query = "software engineering"
    full_query = f"{query} jobs apply"
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(full_query)}"


_WRITABLE_DIR_CACHE: set[Path] = set()


def get_writable_path(path: str | Path) -> Path:
    """Resolve a path that is writable in read-only environments (like Vercel serverless).

    If target directory is not writable or VERCEL environment variable is present,
    returns a path in temp directory while allowing initial reads from the target path.
    """
    target = Path(path)
    is_vercel = os.environ.get("VERCEL") == "1"

    if is_vercel:
        tmp_dir = Path(tempfile.gettempdir()) / "jobhunt"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / target.name

    parent = target.parent if target.parent != Path(".") else Path.cwd()

    if parent in _WRITABLE_DIR_CACHE:
        return target

    parent_writable = True
    try:
        parent.mkdir(parents=True, exist_ok=True)
        test_file = parent / ".writable_test"
        test_file.touch()
        test_file.unlink()
        parent_writable = True
    except (PermissionError, OSError):
        parent_writable = False

    if parent_writable:
        _WRITABLE_DIR_CACHE.add(parent)
        return target
    else:
        tmp_dir = Path(tempfile.gettempdir()) / "jobhunt"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / target.name


def _atomic_replace(src: Path, dst: Path, retries: int = 4, delay: float = 0.05) -> None:
    """Safely replace dst with src, retrying transient Windows file locks."""
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                try:
                    dst.write_bytes(src.read_bytes())
                    src.unlink(missing_ok=True)
                except Exception:
                    os.replace(src, dst)


class Store:
    def __init__(
        self,
        path: str | Path = "state/seen.json",
        user_email: Optional[str] = None,
        token: Optional[str] = None,
        use_service_key: bool = False,
    ):
        self.original_path = Path(path)
        self.user_email = (user_email or "").strip().lower() if user_email else None
        self.token = token
        self.use_service_key = use_service_key
        self.memory = SupabaseMemory(token=self.token)
        self.data: dict[str, dict] = {}

        if self.user_email:
            user_hash = hashlib.md5(self.user_email.encode("utf-8")).hexdigest()[:12]
            parent_dir = self.original_path.parent
            user_target = (
                parent_dir / f"seen_{user_hash}.json"
                if parent_dir != Path(".")
                else Path("state") / f"seen_{user_hash}.json"
            )
            self.path = get_writable_path(user_target)
        else:
            self.path = get_writable_path(self.original_path)

        # 1. Load from local cache / JSON file
        read_target = self.path if self.path.exists() else (self.original_path if not self.user_email else None)
        if read_target and read_target.exists():
            try:
                raw_data = json.loads(read_target.read_text(encoding="utf-8"))
                if isinstance(raw_data, list):
                    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    migrated: dict[str, dict] = {}
                    for item in raw_data:
                        if isinstance(item, str):
                            migrated[item] = {
                                "first_seen": now,
                                "company": "",
                                "title": "",
                                "location": "",
                                "url": sanitize_job_url("", job_id=item),
                                "score": None,
                                "reason": None,
                                "emailed": False,
                                "applied": False,
                                "applied_on": None,
                            }
                        elif isinstance(item, dict) and "job_id" in item:
                            jid = str(item["job_id"])
                            item["url"] = sanitize_job_url(
                                item.get("url"),
                                ats=item.get("ats", ""),
                                job_id=jid,
                                company=item.get("company", ""),
                                title=item.get("title", ""),
                            )
                            migrated[jid] = item
                    self.data = migrated
                    self.save()
                elif isinstance(raw_data, dict):
                    self.data = raw_data
            except json.JSONDecodeError:
                print(f"  ! {read_target} corrupt, starting fresh")

        # 2. If user_email provided and Supabase is configured, pull from Supabase PostgreSQL memory
        if self.user_email and self.memory.is_configured:
            remote_jobs = self.memory.load_user_jobs(self.user_email, token=self.token)
            # Fallback: if user JWT read returned empty, retry with service key
            if not remote_jobs and (self.token or self.use_service_key):
                remote_jobs = self.memory.load_user_jobs(self.user_email, token=None)
            if remote_jobs:
                # Purge local jobs that are no longer present in Supabase remote store
                local_keys = set(self.data.keys())
                remote_keys = set(remote_jobs.keys())
                for k in local_keys - remote_keys:
                    del self.data[k]
                # Merge remote jobs with local store
                for jid, rjob in remote_jobs.items():
                    self.data[jid] = rjob
            elif self.data:
                # Initial cloud sync of existing local jobs for this user
                self.memory.bulk_upsert_user_jobs(
                    self.user_email,
                    list(self.data.values()),
                    token=self.token,
                    use_service_key=self.use_service_key,
                )

        # Ensure all stored jobs have valid, sanitized apply URLs
        changed_urls = False
        for jid, row in list(self.data.items()):
            current_url = row.get("url", "")
            sanitized = sanitize_job_url(
                current_url,
                ats=row.get("ats", ""),
                job_id=jid,
                company=row.get("company", ""),
                title=row.get("title", ""),
            )
            if sanitized != current_url:
                row["url"] = sanitized
                changed_urls = True
        if changed_urls:
            self.save(auto_export=False)

    def unseen(self, jobs: list[Job]) -> list[Job]:
        return [j for j in jobs if j.job_id not in self.data]

    def record(self, jobs: list[Job], emailed: bool = True) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_jobs = []
        for j in jobs:
            clean_url = sanitize_job_url(
                j.url,
                ats=j.ats,
                job_id=j.job_id,
                company=j.company,
                title=j.title,
            )
            job_dict = {
                "job_id": j.job_id,
                "first_seen": now,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "url": clean_url,
                "ats": j.ats or "custom",
                "score": j.score,
                "reason": j.reason,
                "emailed": emailed,
                "applied": False,
                "applied_on": None,
                "application_stage": "to_apply",
                "notes": "",
                "salary_range": j.salary or "",
                "draft": j.draft or {},
            }
            self.data.setdefault(j.job_id, job_dict)
            new_jobs.append(job_dict)
        self.save()

        # Cloud sync to Supabase PostgreSQL memory
        if self.user_email and self.memory.is_configured and new_jobs:
            self.memory.bulk_upsert_user_jobs(
                self.user_email,
                new_jobs,
                token=self.token,
                use_service_key=self.use_service_key,
            )

    def mark_applied(self, job_id: str) -> bool:
        if job_id not in self.data:
            return False
        self.data[job_id]["applied"] = True
        self.data[job_id]["applied_on"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.data[job_id]["application_stage"] = "applied"
        self.save()

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.set_job_applied(self.user_email, job_id, applied=True, token=self.token)
        return True

    def unmark_applied(self, job_id: str) -> bool:
        if job_id not in self.data:
            return False
        self.data[job_id]["applied"] = False
        self.data[job_id]["applied_on"] = None
        self.data[job_id]["application_stage"] = "to_apply"
        self.save()

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.set_job_applied(self.user_email, job_id, applied=False, token=self.token)
        return True

    def update_stage(self, job_id: str, stage: str) -> bool:
        if job_id not in self.data or not stage:
            return False
        clean_stage = stage.lower().strip()
        applied = clean_stage in ("applied", "interviewing", "offer", "rejected")
        self.data[job_id]["application_stage"] = clean_stage
        self.data[job_id]["applied"] = applied
        if applied and not self.data[job_id].get("applied_on"):
            self.data[job_id]["applied_on"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        elif not applied:
            self.data[job_id]["applied_on"] = None
        self.save()

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.set_job_stage(self.user_email, job_id, clean_stage, token=self.token)
        return True

    def update_notes(self, job_id: str, notes: str) -> bool:
        if job_id not in self.data:
            return False
        self.data[job_id]["notes"] = str(notes or "")
        self.save(auto_export=False)

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.set_job_notes(self.user_email, job_id, notes, token=self.token)
        return True

    def delete_job(self, job_id: str) -> bool:
        if job_id not in self.data:
            return False
        del self.data[job_id]
        self.save()

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.delete_user_job(self.user_email, job_id, token=self.token)
        return True

    def add_job(
        self,
        title: str,
        company: str,
        location: str = "Remote/Unspecified",
        url: str = "#",
        ats: str = "custom",
        score: float = 7.5,
        reason: str = "Manually added via Dashboard",
        applied: bool = False,
        draft: dict | None = None,
        job_id: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not job_id:
            safe_company = "".join(c for c in company.lower() if c.isalnum()) or "company"
            ts_str = str(int(datetime.now(timezone.utc).timestamp() * 1000))
            job_id = f"{ats}:{safe_company}:{ts_str}"

        try:
            clamped_score = max(0.0, min(10.0, float(score))) if score is not None else 7.5
        except (ValueError, TypeError):
            clamped_score = 7.5

        clean_url = sanitize_job_url(
            url,
            ats=ats,
            job_id=job_id,
            company=company,
            title=title,
        )

        stage = "applied" if applied else "to_apply"
        job_dict = {
            "job_id": job_id,
            "first_seen": now,
            "company": company,
            "title": title,
            "location": location or "Remote/Unspecified",
            "url": clean_url,
            "ats": ats,
            "score": clamped_score,
            "reason": reason,
            "emailed": False,
            "applied": bool(applied),
            "applied_on": now if applied else None,
            "application_stage": stage,
            "notes": "",
            "salary_range": "",
            "draft": draft or {},
        }
        self.data[job_id] = job_dict
        self.save()

        # Cloud sync to Supabase
        if self.user_email and self.memory.is_configured:
            self.memory.save_user_job(self.user_email, job_dict, token=self.token)

        return job_id

    def stats(self) -> dict:
        return {
            "tracked": len(self.data),
            "emailed": sum(1 for v in self.data.values() if v.get("emailed")),
            "applied": sum(1 for v in self.data.values() if v.get("applied")),
        }

    def export_csv(self, path: str | Path = "out/tracker.csv") -> Path:

        with _CSV_EXPORT_LOCK:
            resolved_path = path
            if str(path) in ("out/tracker.csv", "tracker.csv") and self.user_email:
                user_hash = hashlib.md5(self.user_email.encode("utf-8")).hexdigest()[:12]
                resolved_path = f"out/tracker_{user_hash}.csv"
            target_path = get_writable_path(resolved_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            cols = [
                "first_seen",
                "company",
                "title",
                "location",
                "score",
                "score_100",
                "queue_category",
                "india_eligibility",
                "best_project",
                "reason",
                "applied",
                "applied_on",
                "url",
            ]
            unique_tmp_suffix = f".tmp.{os.getpid()}_{threading.get_ident()}"
            tmp_csv = target_path.with_suffix(unique_tmp_suffix)
            with tmp_csv.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["job_id"] + cols, extrasaction="ignore")
                w.writeheader()
                for jid, row in sorted(self.data.items(), key=lambda kv: kv[1].get("first_seen", ""), reverse=True):
                    score_val = row.get("score")
                    try:
                        score_100 = int(round(max(0.0, min(10.0, float(score_val))) * 10)) if score_val is not None else 0
                    except (ValueError, TypeError):
                        score_100 = 0
                    if score_100 >= 90:
                        cat = "🔥 Exceptional"
                    elif score_100 >= 80:
                        cat = "🟢 Strong Apply"
                    elif score_100 >= 70:
                        cat = "🟡 Apply"
                    elif score_100 >= 60:
                        cat = "⚪ Consider"
                    else:
                        cat = "🔴 Skip"

                    draft = row.get("draft") or {}
                    row_copy = dict(row)
                    row_copy["score_100"] = score_100
                    row_copy["queue_category"] = cat
                    row_copy["india_eligibility"] = draft.get("india_eligibility") or "Verified India-Friendly"
                    row_copy["best_project"] = draft.get("best_project") or "Project Match"
                    w.writerow({"job_id": jid, **row_copy})
            _atomic_replace(tmp_csv, target_path)
            return target_path

    def prune_old_jobs(self) -> None:
        """Keep database footprint small by purging stale jobs under configurable limits."""
        is_prod = (
            os.environ.get("VERCEL") == "1"
            or os.environ.get("FLASK_ENV") == "production"
            or os.environ.get("CI") == "true"
        )
        has_env_limit = "MAX_TRACKED_JOBS_COUNT" in os.environ

        if not is_prod and not has_env_limit:
            return

        max_count = int(os.environ.get("MAX_TRACKED_JOBS_COUNT") or 300)

        if len(self.data) <= max_count:
            return

        keep_stages = {"applied", "interviewing", "offer", "rejected"}
        # Sort so oldest unapplied jobs come first for eviction
        sorted_jobs = sorted(
            self.data.items(),
            key=lambda x: (
                bool(x[1].get("applied")),
                x[1].get("application_stage", "") in keep_stages,
                x[1].get("first_seen") or x[1].get("created_at") or "",
            ),
        )

        excess_count = len(self.data) - max_count
        purged = 0
        for jid, job in sorted_jobs:
            if excess_count <= 0:
                break

            is_applied = bool(job.get("applied"))
            stage = job.get("application_stage")
            if is_applied or stage in keep_stages:
                continue

            del self.data[jid]
            excess_count -= 1
            purged += 1

            if self.user_email and self.memory.is_configured:
                try:
                    self.memory.delete_user_job(self.user_email, jid, token=self.token)
                except Exception:
                    pass

        if purged > 0:
            print(f"  [prune] purged {purged} stale jobs to stay under free storage limits (capped at {max_count}).")

    def save(self, auto_export: bool = True) -> None:
        self.prune_old_jobs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        unique_tmp_suffix = f".tmp.{os.getpid()}_{threading.get_ident()}"
        tmp = self.path.with_suffix(unique_tmp_suffix)
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        _atomic_replace(tmp, self.path)
        if auto_export:
            try:
                self.export_csv()
            except Exception as e:
                print(f"  ! Store auto-export CSV warning: {e}")


def init(
    path: str | Path = "seen.json",
    user_email: Optional[str] = None,
    token: Optional[str] = None,
    use_service_key: bool = False,
) -> Store:
    return Store(path, user_email=user_email, token=token, use_service_key=use_service_key)


def unseen(store: Store, jobs: list[Job]) -> list[Job]:
    return store.unseen(jobs)


def record(store: Store, jobs: list[Job], emailed: bool = True) -> None:
    store.record(jobs, emailed=emailed)


def mark_applied(store: Store, job_id: str) -> bool:
    return store.mark_applied(job_id)


def unmark_applied(store: Store, job_id: str) -> bool:
    return store.unmark_applied(job_id)


def delete_job(store: Store, job_id: str) -> bool:
    return store.delete_job(job_id)


def add_job(store: Store, **kwargs) -> str:
    return store.add_job(**kwargs)


def export_csv(store: Store, path: str | Path = "out/tracker.csv") -> Path:
    return store.export_csv(path)

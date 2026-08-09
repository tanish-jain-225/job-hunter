"""seen.json doubles as the dedupe index AND the application tracker."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .fetch import Job


def get_writable_path(path: str | Path) -> Path:
    """Resolve a path that is writable in read-only environments (like Vercel serverless).

    If target directory is not writable or VERCEL environment variable is present,
    returns a path in temp directory while allowing initial reads from the target path.
    """
    target = Path(path)
    is_vercel = os.environ.get("VERCEL") == "1" or "VERCEL" in os.environ

    parent = target.parent if target.parent != Path(".") else Path.cwd()
    parent_writable = True
    if is_vercel:
        parent_writable = False
    else:
        try:
            parent.mkdir(parents=True, exist_ok=True)
            test_file = parent / ".writable_test"
            test_file.touch()
            test_file.unlink()
        except (PermissionError, OSError):
            parent_writable = False

    if parent_writable:
        return target
    else:
        tmp_dir = Path(tempfile.gettempdir()) / "jobhunt"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / target.name


class Store:
    def __init__(self, path: str | Path = "seen.json"):
        self.original_path = Path(path)
        self.path = get_writable_path(self.original_path)
        self.data: dict[str, dict] = {}

        read_target = self.path if self.path.exists() else self.original_path
        if read_target.exists():
            try:
                self.data = json.loads(read_target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"  ! {read_target} corrupt, starting fresh")

    def unseen(self, jobs: list[Job]) -> list[Job]:
        return [j for j in jobs if j.job_id not in self.data]

    def record(self, jobs: list[Job], emailed: bool = True) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for j in jobs:
            self.data.setdefault(j.job_id, {
                "first_seen": now,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "url": j.url,
                "score": j.score,
                "reason": j.reason,
                "emailed": emailed,
                "applied": False,
                "applied_on": None,
            })
        self.save()

    def mark_applied(self, job_id: str) -> bool:
        if job_id not in self.data:
            return False
        self.data[job_id]["applied"] = True
        self.data[job_id]["applied_on"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save()
        return True

    def stats(self) -> dict:
        return {
            "tracked": len(self.data),
            "emailed": sum(1 for v in self.data.values() if v.get("emailed")),
            "applied": sum(1 for v in self.data.values() if v.get("applied")),
        }

    def export_csv(self, path: str | Path = "out/tracker.csv") -> Path:
        target_path = get_writable_path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        cols = ["first_seen", "company", "title", "location", "score",
                "reason", "applied", "applied_on", "url"]
        with target_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["job_id"] + cols, extrasaction="ignore")
            w.writeheader()
            for jid, row in sorted(self.data.items(),
                                   key=lambda kv: kv[1].get("first_seen", ""), reverse=True):
                w.writerow({"job_id": jid, **row})
        return target_path

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.path)


def init(path: str | Path = "seen.json") -> Store:
    return Store(path)


def unseen(store: Store, jobs: list[Job]) -> list[Job]:
    return store.unseen(jobs)


def record(store: Store, jobs: list[Job], emailed: bool = True) -> None:
    store.record(jobs, emailed=emailed)


def mark_applied(store: Store, job_id: str) -> bool:
    return store.mark_applied(job_id)


def export_csv(store: Store, path: str | Path = "out/tracker.csv") -> Path:
    return store.export_csv(path)


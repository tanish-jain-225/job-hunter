"""Workspace cleanup utility module for Job Hunter (`jobhunt clean`).

Purges temporary test stores (seen_*.json), transient test artifacts, and leftover
scratch files from workspace root without modifying user configuration or primary stores.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_cleanable_files(root: Path | str | None = None) -> list[Path]:
    """Identify temporary and transient files suitable for safe removal."""
    base = Path(root).resolve() if root else Path.cwd().resolve()
    cleanable: list[Path] = []

    # Protected core filenames that must NEVER be deleted
    protected = {
        "seen.json",
        "tracker.csv",
        "config.yaml",
        "config.example.yaml",
        "companies.yaml",
        "profile.json",
        "profile.example.json",
        "resume.pdf",
        ".env",
        ".env.example",
        "digest.html",
    }

    try:
        dirs_to_scan = [base]
        for sub in ("state", "out", "scratch"):
            sub_dir = base / sub
            if sub_dir.is_dir():
                dirs_to_scan.append(sub_dir)

        for search_dir in dirs_to_scan:
            for p in search_dir.iterdir():
                if p.is_dir():
                    continue
                name = p.name
                if name in protected:
                    continue

                # 1. Target leftover seen_*.json test/scratch stores (e.g. seen_111d68d06e2d.json, seen_test_cli.json)
                if name.startswith("seen_") and name.endswith(".json"):
                    cleanable.append(p)
                # 2. Target leftover user-scoped test profiles (e.g. profile_255921b9d80f.json)
                elif name.startswith("profile_") and name.endswith(".json") and name != "profile.example.json":
                    cleanable.append(p)
                # 3. Target temporary export artifacts and user tracker CSVs (e.g. .tracker-*.csv, tracker_*.csv)
                elif (name.startswith(".tracker-") or name.startswith("tracker_")) and name.endswith(".csv"):
                    cleanable.append(p)
                # 4. Target coverage reports and temporary write test artifacts
                elif name == ".coverage" or name.startswith(".writable_test") or name.endswith(".tmp") or name.endswith(".bak"):
                    cleanable.append(p)
                # 5. Any transient files inside scratch/
                elif search_dir.name == "scratch":
                    cleanable.append(p)
    except Exception as e:
        logger.warning("Error scanning directory for cleanup: %s", e)

    return sorted(cleanable)


def clean_workspace(root: Path | str | None = None, dry_run: bool = False) -> tuple[list[Path], int]:
    """Execute cleanup of temporary files in workspace root.

    Returns:
        tuple[list[Path], int]: (list of removed file paths, total bytes freed)
    """
    targets = find_cleanable_files(root)
    removed: list[Path] = []
    freed_bytes = 0

    for target in targets:
        try:
            size = target.stat().st_size if target.exists() else 0
            if not dry_run:
                target.unlink(missing_ok=True)
            removed.append(target)
            freed_bytes += size
        except Exception as e:
            logger.warning("Could not remove temporary file %s: %s", target, e)

    return removed, freed_bytes

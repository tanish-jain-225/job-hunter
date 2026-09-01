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
        "config.yaml",
        "config.example.yaml",
        "companies.yaml",
        "profile.json",
        "profile.example.json",
        "resume.pdf",
        ".env",
        ".env.example",
    }

    try:
        dirs_to_scan = [base]
        state_dir = base / "state"
        if state_dir.is_dir():
            dirs_to_scan.append(state_dir)

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
                # 2. Target temporary write tests or transient atomic files
                elif name.startswith(".writable_test") or name.endswith(".tmp") or name.endswith(".bak"):
                    cleanable.append(p)
    except Exception as e:
        logger.warning(f"Error scanning directory for cleanup: {e}")

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
            logger.warning(f"Could not remove temporary file {target}: {e}")

    return removed, freed_bytes

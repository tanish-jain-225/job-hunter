"""Command-line interface (`jobhunt ...`).

Commands:
  run       Fetch -> prefilter -> LLM screen -> LLM draft -> digest.html
  applied   Mark a job ID as applied so it stops showing up in digests
  stats     Report total tracked jobs and application counts
  profile   Extract candidate profile from a resume (PDF/text) -> profile.json
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import digest, llm, mailer
from .fetch import fetch_all
from .mock import fetch_all_mock
from .prefilter import prefilter
from .providers import LLMError, resolve
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def _resolve_relative(p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    if path.is_file():
        return path
    if os.environ.get("VERCEL") == "1" or "VERCEL" in os.environ:
        root_path = ROOT / path
        if root_path.is_file():
            return root_path
    return path


def _load_env() -> None:
    """Minimal .env loader (no third-party dependency)."""
    env_path = _resolve_relative(Path(".env"))
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _cfg(config_path: str | Path | None = None, raise_on_error: bool = True) -> dict:
    _load_env()
    p = _resolve_relative(Path(config_path) if config_path else Path("config.yaml"))
    if not p.is_file():
        example = _resolve_relative(Path("config.example.yaml"))
        if example.is_file() and config_path is None:
            print("  ! config.yaml not found — falling back to config.example.yaml")
            p = example
        else:
            if raise_on_error:
                sys.exit(f"Error: config file {p} not found.")
            print(f"  ! config file {p} not found, returning default config.")
            return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        if raise_on_error:
            sys.exit(f"Error reading config {p}: {e}")
        print(f"  ! Error reading config {p}: {e}")
        return {}


def _load_profile(cfg: dict, raise_on_error: bool = True) -> dict:
    path = _resolve_relative(Path(cfg.get("profile_file", "profile.json")))
    if not path.is_file():
        sample = _resolve_relative(Path("profile.example.json"))
        if sample.is_file():
            print("  ! profile.json not found — falling back to profile.example.json")
            path = sample
        else:
            if raise_on_error:
                sys.exit(f"Error: {path} missing. Run `jobhunt profile --resume <pdf>` first.")
            print(f"  ! profile file {path} missing, using empty profile.")
            return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        if raise_on_error:
            sys.exit(f"Error reading profile {path}: {e}")
        print(f"  ! Error reading profile {path}: {e}")
        return {}



def _fetch_jobs(args: argparse.Namespace, cfg: dict) -> tuple[list, list]:
    """Stage 1-2: Fetch raw jobs and apply prefilter + dedupe."""
    fetch_max_workers = int(cfg.get("fetch_max_workers", 8))
    filters = cfg.get("filters", {})

    print("[1/5] fetching boards")
    if args.mock:
        raw_jobs = fetch_all_mock()
    else:
        companies_file = _resolve_relative(Path(cfg.get("companies_file", "companies.yaml")))
        raw_jobs = fetch_all(companies_file, max_workers=fetch_max_workers)

    print("\n[2/5] filtering")
    candidates = prefilter(raw_jobs, filters)
    return raw_jobs, candidates



def _screen_jobs(jobs: list, profile: dict, args: argparse.Namespace, cfg: dict) -> None:
    """Stage 3: Score jobs via LLM or keyword matcher."""
    scorer = getattr(args, "scorer", "llm")
    llm_max_workers = int(cfg.get("llm_max_workers", 1))
    llm_delay_seconds = float(cfg.get("llm_delay_seconds", 2.5))

    if scorer == "keyword":
        print("\n[3/5] screening via keyword matcher (DEV ONLY)")
        llm.keyword_screen(jobs, profile)
    else:
        try:
            provider, model = resolve("screen")
        except LLMError as e:
            print(f"\n{e}\nNo key? Run with --scorer keyword for an offline dry run.")
            raise
        print(f"\n[3/5] screening {len(jobs)} jobs via {provider.name}/{model}")
        llm.screen(jobs, profile,
                   batch_size=int(cfg.get("screen_batch_size", 7)),
                   jd_chars=int(cfg.get("screen_jd_chars", 1400)),
                   provider=provider, model=model,
                   delay_seconds=llm_delay_seconds,
                   max_workers=llm_max_workers)

    # Fallback to keyword screening if all LLM screening attempts failed
    if scorer == "llm" and not any(j.score is not None for j in jobs):
        print("\n! LLM screening rate-limited or failed. Falling back to keyword scorer to produce digest...")
        llm.keyword_screen(jobs, profile)


def _select_shortlist(jobs: list, cfg: dict) -> tuple[list, list]:
    """Select scored jobs and build the shortlist above the threshold."""
    unscored_count = sum(1 for j in jobs if j.score is None)
    if unscored_count > 0:
        print(f"\n  ! Warning: {unscored_count}/{len(jobs)} jobs could not be scored by LLM.\n"
              f"    Only successfully scored jobs will be saved to seen.json (unscored jobs will be retried next run).")

    threshold = float(cfg.get("score_threshold", 7.0))
    top_n = int(cfg.get("max_per_digest", 7))

    scored_jobs = [j for j in jobs if j.score is not None]
    shortlist = [j for j in scored_jobs if (j.score or 0) >= threshold]
    shortlist.sort(key=lambda j: j.score or 0, reverse=True)
    shortlist = shortlist[:top_n]

    print(f"\n  {len(shortlist)} jobs cleared the {threshold} bar")
    return scored_jobs, shortlist


def _draft_kits(shortlist: list, profile: dict, scorer: str, cfg: dict) -> None:
    """Stage 4: Generate application kits for the shortlist."""
    llm_delay_seconds = float(cfg.get("llm_delay_seconds", 2.5))

    if shortlist and scorer == "llm":
        try:
            d_provider, d_model = resolve("draft")
            print(f"\n[4/5] drafting kits via {d_provider.name}/{d_model}")
            llm.draft(shortlist, profile,
                      jd_chars=int(cfg.get("draft_jd_chars", 7000)),
                      provider=d_provider, model=d_model,
                      delay_seconds=llm_delay_seconds)
        except LLMError as e:
            print(f"\n  ! Draft provider failed: {e}. Proceeding with empty kits.")


def _build_and_send_digest(shortlist: list, raw_jobs: list, candidates: list,
                           scored_jobs: list, st, args: argparse.Namespace,
                           cfg: dict, profile: dict | None = None) -> None:
    """Stage 5: Build digest HTML, export CSV, and optionally send email."""
    print("\n[5/5] building digest")
    out_html = Path(cfg.get("digest_file", "out/digest.html"))
    tracker_csv = Path(cfg.get("tracker_csv", "out/tracker.csv"))

    subject, html_content = digest.build(
        shortlist,
        scanned=len(raw_jobs),
        candidates=len(candidates),
        stats=st.stats(),
        profile=profile,
    )
    digest.write(html_content, out_html)
    print(f"  wrote {out_html}")

    st.record(scored_jobs, emailed=args.send)
    st.export_csv(tracker_csv)

    if args.send:
        print("\n[mailing digest]")
        mailer.send(subject, html_content)


def cmd_run(args: argparse.Namespace) -> int:
    """Orchestrate the full pipeline: fetch → filter → screen → draft → digest."""
    cfg = _cfg(getattr(args, "config", None))
    profile = _load_profile(cfg)
    seen_file = cfg.get("seen_file", "seen.json")

    # 1-2. Fetch + filter
    raw_jobs, candidates = _fetch_jobs(args, cfg)
    st = Store(seen_file)
    jobs = st.unseen(candidates)
    print(f"  new since last run: {len(jobs)}")

    if not jobs:
        print("\nNo new matching jobs today.")
        if getattr(args, "send", False):
            _build_and_send_digest([], raw_jobs, candidates, [], st, args, cfg, profile=profile)
        return 0

    # 3. Screen
    try:
        _screen_jobs(jobs, profile, args, cfg)
    except LLMError:
        return 1

    # 4. Shortlist + draft
    scored_jobs, shortlist = _select_shortlist(jobs, cfg)
    scorer = getattr(args, "scorer", "llm")
    _draft_kits(shortlist, profile, scorer, cfg)

    # 5. Digest + mail
    _build_and_send_digest(shortlist, raw_jobs, candidates, scored_jobs, st, args, cfg, profile=profile)

    return 0


def cmd_applied(args: argparse.Namespace) -> int:
    cfg = _cfg(getattr(args, "config", None))
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = Path(cfg.get("tracker_csv", "out/tracker.csv"))
    st = Store(seen_file)
    if st.mark_applied(args.job_id):
        st.export_csv(tracker_csv)
        print(f"Marked {args.job_id} as applied.")
        return 0
    else:
        print(f"Job ID {args.job_id} not found in {seen_file}.")
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = _cfg(getattr(args, "config", None))
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = Path(cfg.get("tracker_csv", "out/tracker.csv"))
    st = Store(seen_file)
    st.export_csv(tracker_csv)
    stats_dict = st.stats()
    print(f"Total tracked jobs: {stats_dict['tracked']}")
    print(f"Total emailed: {stats_dict['emailed']}")
    print(f"Total applied: {stats_dict['applied']}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    _load_env()
    resume_path = Path(args.resume)
    if not resume_path.is_file():
        sys.exit(f"Error: resume file {resume_path} not found.")

    is_pdf = resume_path.suffix.lower() == ".pdf"
    resume_bytes = resume_path.read_bytes() if is_pdf else None
    resume_text = None if is_pdf else resume_path.read_text(encoding="utf-8", errors="ignore")

    try:
        provider, model = resolve("draft")
    except LLMError as e:
        sys.exit(f"Error resolving LLM provider: {e}")

    print(f"reading {resume_path} via {provider.name}/{model} ...")
    prof = llm.build_profile(resume_bytes=resume_bytes, resume_text=resume_text,
                             is_pdf=is_pdf, provider=provider, model=model)

    out_file = Path("profile.json")
    out_file.write_text(yaml.dump(prof) if args.yaml else json_dumps_pretty(prof), encoding="utf-8")
    print(f"wrote {out_file}\n")
    print(json_dumps_pretty(prof))
    return 0


def json_dumps_pretty(obj: dict) -> str:
    import json
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobhunt", description="Personal job-search agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Fetch, filter, score, and draft digest.")
    p_run.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    p_run.add_argument("--mock", action="store_true", help="Use mock ATS data (no network).")
    p_run.add_argument("--send", action="store_true", help="Send digest email via SMTP.")
    p_run.add_argument("--scorer", choices=["llm", "keyword"], default="llm",
                       help="Scorer to use (default: llm).")

    # applied
    p_applied = subparsers.add_parser("applied", help="Mark a job ID as applied.")
    p_applied.add_argument("job_id", help="Exact job ID (e.g. greenhouse:acme:5501001).")
    p_applied.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")

    # stats
    p_stats = subparsers.add_parser("stats", help="Report stats on tracked jobs.")
    p_stats.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")

    # profile
    p_prof = subparsers.add_parser("profile", help="Extract profile from resume.")
    p_prof.add_argument("--resume", required=True, help="Path to resume file (PDF or text).")
    p_prof.add_argument("--yaml", action="store_true", help="Save as YAML instead of JSON.")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "applied":
        sys.exit(cmd_applied(args))
    elif args.command == "stats":
        sys.exit(cmd_stats(args))
    elif args.command == "profile":
        sys.exit(cmd_profile(args))


if __name__ == "__main__":
    main()

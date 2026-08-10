"""Unit tests for jobhunt.store (Store class for seen.json dedupe and tracker)."""
from __future__ import annotations

import json
from pathlib import Path

from jobhunt import store
from jobhunt.fetch import Job
from jobhunt.store import Store


def test_store_init_creates_fresh_when_missing(tmp_path: Path):
    path = tmp_path / "seen.json"
    store = Store(path)
    assert store.data == {}


def test_store_init_handles_corrupt_file(tmp_path: Path):
    path = tmp_path / "seen.json"
    path.write_text("invalid json content {{{", encoding="utf-8")
    store = Store(path)
    assert store.data == {}


def test_store_unseen_filters_correctly(tmp_path: Path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"greenhouse:acme:1": {"title": "SDE"}}), encoding="utf-8")
    store = Store(path)

    j1 = Job("greenhouse:acme:1", "greenhouse", "Acme", "SDE", "Bangalore", "http://ex.com/1", "desc")
    j2 = Job("greenhouse:acme:2", "greenhouse", "Acme", "SDE II", "Bangalore", "http://ex.com/2", "desc")

    unseen = store.unseen([j1, j2])
    assert len(unseen) == 1
    assert unseen[0].job_id == "greenhouse:acme:2"


def test_store_record_and_mark_applied(tmp_path: Path):
    path = tmp_path / "seen.json"
    store = Store(path)

    j1 = Job("greenhouse:acme:1", "greenhouse", "Acme", "SDE", "Bangalore", "http://ex.com/1", "desc", score=8.5)
    store.record([j1], emailed=True)

    assert "greenhouse:acme:1" in store.data
    assert store.data["greenhouse:acme:1"]["emailed"] is True
    assert store.data["greenhouse:acme:1"]["applied"] is False

    ok = store.mark_applied("greenhouse:acme:1")
    assert ok is True
    assert store.data["greenhouse:acme:1"]["applied"] is True
    assert store.data["greenhouse:acme:1"]["applied_on"] is not None

    # Unknown job ID mark_applied returns False
    assert store.mark_applied("nonexistent_id") is False


def test_store_export_csv(tmp_path: Path):
    seen_path = tmp_path / "seen.json"
    csv_path = tmp_path / "out" / "tracker.csv"
    store = Store(seen_path)

    j1 = Job("greenhouse:acme:1", "greenhouse", "Acme", "SDE", "Bangalore", "http://ex.com/1", "desc", score=8.5)
    store.record([j1], emailed=False)

    exported = store.export_csv(csv_path)
    assert exported.exists()
    content = exported.read_text(encoding="utf-8")
    assert "job_id" in content
    assert "greenhouse:acme:1" in content
    assert "Acme" in content


def test_store_module_helpers(tmp_path: Path):
    path = tmp_path / "seen.json"
    st = store.init(path)
    assert isinstance(st, Store)

    j1 = Job("greenhouse:acme:1", "greenhouse", "Acme", "SDE", "Bangalore", "http://ex.com/1", "desc", score=8.5)
    unseen_jobs = store.unseen(st, [j1])
    assert len(unseen_jobs) == 1

    store.record(st, [j1], emailed=True)
    assert len(store.unseen(st, [j1])) == 0

    assert store.mark_applied(st, "greenhouse:acme:1") is True
    assert store.mark_applied(st, "invalid") is False

    csv_path = store.export_csv(st, tmp_path / "tracker.csv")
    assert csv_path.exists()


def test_store_unmark_delete_and_add_job(tmp_path: Path):
    path = tmp_path / "seen.json"
    st = Store(path)

    # 1. Add job
    job_id = st.add_job(
        title="Backend Engineer",
        company="Stripe",
        location="Remote",
        url="https://stripe.com/jobs/123",
        score=8.5,
        applied=True,
    )
    assert job_id in st.data
    assert st.data[job_id]["title"] == "Backend Engineer"
    assert st.data[job_id]["applied"] is True
    assert st.stats()["applied"] == 1
    assert st.stats()["tracked"] == 1

    # 2. Unmark applied
    assert st.unmark_applied(job_id) is True
    assert st.data[job_id]["applied"] is False
    assert st.data[job_id]["applied_on"] is None
    assert st.stats()["applied"] == 0

    # 3. Unmark non-existent job returns False
    assert st.unmark_applied("nonexistent_id") is False

    # 4. Module helpers for unmark, delete, and add
    added_id = store.add_job(st, title="Frontend Dev", company="Vercel", score=9.0)
    assert added_id in st.data
    assert store.unmark_applied(st, added_id) is True

    # 5. Delete job
    assert store.delete_job(st, job_id) is True
    assert job_id not in st.data
    assert store.delete_job(st, "nonexistent_id") is False


def test_store_auto_csv_export_sync(tmp_path: Path, monkeypatch):
    """Verify Store.save() automatically updates out/tracker.csv."""
    seen_path = tmp_path / "seen.json"
    csv_path = tmp_path / "out" / "tracker.csv"
    monkeypatch.chdir(tmp_path)

    st = Store(seen_path)
    job_id = st.add_job(title="Staff Engineer", company="GitHub", score=9.5)

    assert csv_path.exists()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert job_id in csv_text
    assert "GitHub" in csv_text


def test_store_score_clamping(tmp_path: Path):
    """Verify score clamping to 0.0-10.0 in add_job."""
    seen_path = tmp_path / "seen.json"
    st = Store(seen_path)

    j1 = st.add_job(title="High Score Job", company="Acme", score=15.0)
    j2 = st.add_job(title="Low Score Job", company="Acme", score=-5.0)

    assert st.data[j1]["score"] == 10.0
    assert st.data[j2]["score"] == 0.0


def test_load_seen_legacy_array(tmp_path: Path):
    """Test migrating legacy JSON array format."""
    file_path = tmp_path / "seen.json"
    legacy_data = ["job_1", "job_2"]
    file_path.write_text(json.dumps(legacy_data), encoding="utf-8")

    st = Store(storage_file=file_path) if hasattr(Store, "storage_file") else Store(file_path)
    assert "job_1" in st.data
    assert "job_2" in st.data
    assert st.data["job_1"]["first_seen"] is not None




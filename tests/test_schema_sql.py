"""Unit tests for Supabase SQL schema and teardown scripts integrity."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "supabase" / "schema.sql"
TEARDOWN_PATH = REPO_ROOT / "supabase" / "teardown.sql"


def test_schema_files_exist():
    assert SCHEMA_PATH.is_file(), "supabase/schema.sql must exist"
    assert TEARDOWN_PATH.is_file(), "supabase/teardown.sql must exist"


def test_schema_and_teardown_transaction_safety():
    """Both scripts must be wrapped in atomic transactions (BEGIN ... COMMIT)."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    teardown_sql = TEARDOWN_PATH.read_text(encoding="utf-8")

    # Verify BEGIN and COMMIT exist in both files
    assert "BEGIN;" in schema_sql, "schema.sql must start an atomic transaction with BEGIN;"
    assert "COMMIT;" in schema_sql, "schema.sql must commit the transaction with COMMIT;"
    assert "BEGIN;" in teardown_sql, "teardown.sql must start an atomic transaction with BEGIN;"
    assert "COMMIT;" in teardown_sql, "teardown.sql must commit the transaction with COMMIT;"


def test_schema_tables_and_foreign_keys():
    """schema.sql must create all 3 tables with proper foreign key cascades."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    expected_tables = [
        "public.user_profiles",
        "public.user_tracked_jobs",
        "public.user_pipeline_runs",
    ]
    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema_sql, f"Missing table creation: {table}"

    # Verify foreign key cascade from user_tracked_jobs to user_profiles
    assert "REFERENCES public.user_profiles(email) ON DELETE CASCADE" in schema_sql

    # Verify foreign key cascade constraint on user_pipeline_runs
    assert "fk_user_pipeline_runs_email" in schema_sql


def test_schema_rls_and_security_policies():
    """All tables must enable RLS and specify tenant isolation policies."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    expected_tables = [
        "public.user_profiles",
        "public.user_tracked_jobs",
        "public.user_pipeline_runs",
    ]
    for table in expected_tables:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in schema_sql

    # Verify auth.jwt() subquery optimization and service_role bypass
    assert "(select auth.jwt())" in schema_sql
    assert "'service_role'" in schema_sql

    # Verify consolidated profile policy
    assert "Allow user to manage own profile" in schema_sql


def test_schema_trigger_function_search_path():
    """Trigger function must explicitly define secure search path."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "SET search_path = public, pg_temp" in schema_sql
    assert "CREATE OR REPLACE FUNCTION public.handle_updated_at()" in schema_sql


def test_teardown_symmetry_with_schema():
    """Every table, sequence, and function created in schema must be dropped in teardown."""
    teardown_sql = TEARDOWN_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS public.user_tracked_jobs CASCADE;" in teardown_sql
    assert "DROP TABLE IF EXISTS public.user_pipeline_runs CASCADE;" in teardown_sql
    assert "DROP TABLE IF EXISTS public.user_profiles CASCADE;" in teardown_sql

    assert "DROP SEQUENCE IF EXISTS public.user_tracked_jobs_id_seq CASCADE;" in teardown_sql
    assert "DROP SEQUENCE IF EXISTS public.user_pipeline_runs_id_seq CASCADE;" in teardown_sql

    assert "DROP FUNCTION IF EXISTS public.handle_updated_at() CASCADE;" in teardown_sql


def _extract_table_columns(schema_sql: str, table: str) -> set[str]:
    """Return every column name defined in CREATE TABLE or ALTER TABLE ADD COLUMN for *table*."""
    import re

    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS public\.{table}\s*\((.*?)\n\);",
        schema_sql,
        flags=re.DOTALL,
    )
    assert m, f"Could not find CREATE TABLE block for public.{table}"
    cols: set[str] = set()
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("--", "CONSTRAINT ", "PRIMARY KEY", "UNIQUE ")):
            continue
        col = stripped.split()[0]
        cols.add(col)

    for alter_col in re.findall(
        rf"ALTER TABLE public\.{table}\s+ADD COLUMN IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        schema_sql,
    ):
        cols.add(alter_col)
    return cols


def test_postgrest_batch_profile_and_jobs_columns_exist_in_schema():
    """Every explicit PostgREST select column in multi.py and memory.py must exist in schema.sql."""
    from jobhunt.multi import _BATCH_PROFILE_COLUMNS

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    profile_cols = _extract_table_columns(schema_sql, "user_profiles")
    selected_profile_cols = [c.strip() for c in _BATCH_PROFILE_COLUMNS.split(",") if c.strip()]
    missing_profile_cols = [c for c in selected_profile_cols if c not in profile_cols]
    assert not missing_profile_cols, (
        f"_BATCH_PROFILE_COLUMNS contains columns missing from public.user_profiles: {missing_profile_cols}"
    )

    jobs_cols = _extract_table_columns(schema_sql, "user_tracked_jobs")
    memory_src = (REPO_ROOT / "jobhunt" / "memory.py").read_text(encoding="utf-8")
    import re

    m = re.search(r'"select":\s*"(job_id[^"]+)"', memory_src)
    assert m, "Expected explicit select column list for user_tracked_jobs in jobhunt/memory.py"
    selected_job_cols = [c.strip() for c in m.group(1).split(",") if c.strip()]
    missing_job_cols = [c for c in selected_job_cols if c not in jobs_cols]
    assert not missing_job_cols, (
        f"memory.py user_tracked_jobs select contains missing columns: {missing_job_cols}"
    )

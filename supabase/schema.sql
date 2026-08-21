-- ==============================================================================
-- Job Hunter — Supabase PostgreSQL Multi-Tenant Persistent Memory Schema
-- Primary Key: User's Authenticated Email (email / user_email)
-- Features: Strict Tenant Isolation (RLS), Resume Studio, Notification Preferences
-- ==============================================================================

-- 1. Create User Profiles Table (Primary Key: email)
CREATE TABLE IF NOT EXISTS public.user_profiles (
    email TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    title TEXT DEFAULT '',
    education TEXT DEFAULT '',
    experience_years NUMERIC DEFAULT 0,
    skills TEXT[] DEFAULT '{}',
    target_keywords TEXT[] DEFAULT '{}',
    exclude_keywords TEXT[] DEFAULT '{}',
    profile_json JSONB DEFAULT '{}'::jsonb,
    resume_text TEXT DEFAULT '',
    resume_filename TEXT DEFAULT '',
    email_notifications_enabled BOOLEAN DEFAULT FALSE,
    notification_email TEXT DEFAULT '',
    min_score_notification NUMERIC DEFAULT 7.5,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    preferred_locations TEXT[] DEFAULT '{}',
    job_types TEXT[] DEFAULT '{}',
    experience_level TEXT DEFAULT '',
    min_salary_lpa NUMERIC DEFAULT 0,
    preferred_sectors TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure columns exist if table was previously created (safe for re-runs)
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS resume_text TEXT DEFAULT '';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS resume_filename TEXT DEFAULT '';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS notification_email TEXT DEFAULT '';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS min_score_notification NUMERIC DEFAULT 7.5;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS preferred_locations TEXT[] DEFAULT '{}';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS job_types TEXT[] DEFAULT '{}';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS experience_level TEXT DEFAULT '';
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS min_salary_lpa NUMERIC DEFAULT 0;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS preferred_sectors TEXT[] DEFAULT '{}';

-- Back-fill: mark existing users who already have real data as onboarding complete
-- (avoids forcing existing real users through setup wizard again)
UPDATE public.user_profiles
SET onboarding_completed = TRUE
WHERE onboarding_completed = FALSE
  AND name IS NOT NULL AND name != '' AND name != 'Candidate'
  AND array_length(skills, 1) > 0;

-- Index on user_profiles
CREATE INDEX IF NOT EXISTS idx_user_profiles_updated_at ON public.user_profiles (updated_at DESC);

-- ------------------------------------------------------------------------------
-- 2. Create User Tracked Jobs Table (Keyed by user_email + job_id)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_tracked_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_email TEXT NOT NULL REFERENCES public.user_profiles(email) ON DELETE CASCADE,
    job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT 'Remote/Unspecified',
    url TEXT DEFAULT '#',
    ats TEXT DEFAULT 'custom',
    score NUMERIC DEFAULT 0.0,
    reason TEXT,
    applied BOOLEAN DEFAULT FALSE,
    applied_on TIMESTAMPTZ,
    application_stage TEXT DEFAULT 'to_apply',
    notes TEXT DEFAULT '',
    salary_range TEXT DEFAULT '',
    emailed BOOLEAN DEFAULT FALSE,
    draft JSONB DEFAULT '{}'::jsonb,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_job UNIQUE (user_email, job_id)
);

-- Safe migrations for existing deployments
ALTER TABLE public.user_tracked_jobs ADD COLUMN IF NOT EXISTS application_stage TEXT DEFAULT 'to_apply';
ALTER TABLE public.user_tracked_jobs ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';
ALTER TABLE public.user_tracked_jobs ADD COLUMN IF NOT EXISTS salary_range TEXT DEFAULT '';

-- Backfill application_stage from applied boolean
UPDATE public.user_tracked_jobs
SET application_stage = 'applied'
WHERE applied = TRUE AND (application_stage = 'to_apply' OR application_stage IS NULL);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_user_tracked_jobs_email_score ON public.user_tracked_jobs (user_email, score DESC);
CREATE INDEX IF NOT EXISTS idx_user_tracked_jobs_email_applied ON public.user_tracked_jobs (user_email, applied);
CREATE INDEX IF NOT EXISTS idx_user_tracked_jobs_email_stage ON public.user_tracked_jobs (user_email, application_stage);
CREATE INDEX IF NOT EXISTS idx_user_tracked_jobs_email_ats ON public.user_tracked_jobs (user_email, ats);
CREATE INDEX IF NOT EXISTS idx_user_tracked_jobs_created_at ON public.user_tracked_jobs (created_at DESC);

-- ------------------------------------------------------------------------------
-- 3. Create User Pipeline Execution History Table
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_pipeline_runs (
    id BIGSERIAL PRIMARY KEY,
    user_email TEXT NOT NULL,
    run_timestamp TIMESTAMPTZ DEFAULT NOW(),
    jobs_scanned INTEGER DEFAULT 0,
    candidates_matched INTEGER DEFAULT 0,
    shortlisted INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed',
    logs TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_pipeline_runs_email ON public.user_pipeline_runs (user_email, run_timestamp DESC);

-- ------------------------------------------------------------------------------
-- 4. Auto-update updated_at Trigger Function
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_user_profiles_updated_at ON public.user_profiles;
CREATE TRIGGER trigger_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trigger_user_tracked_jobs_updated_at ON public.user_tracked_jobs;
CREATE TRIGGER trigger_user_tracked_jobs_updated_at
    BEFORE UPDATE ON public.user_tracked_jobs
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- ------------------------------------------------------------------------------
-- 5. Enable Row Level Security (RLS) for Strict Multi-Tenancy
-- ------------------------------------------------------------------------------
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_tracked_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_pipeline_runs ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------------------------
-- 6. Row Level Security Policies (Strict Tenant Isolation)
-- ------------------------------------------------------------------------------

-- user_profiles Policies
DROP POLICY IF EXISTS "Allow user to view own profile" ON public.user_profiles;
CREATE POLICY "Allow user to view own profile"
    ON public.user_profiles FOR SELECT
    USING ((auth.jwt() ->> 'email') = email OR (auth.jwt() ->> 'role') = 'service_role');

DROP POLICY IF EXISTS "Allow user to insert/update own profile" ON public.user_profiles;
CREATE POLICY "Allow user to insert/update own profile"
    ON public.user_profiles FOR ALL
    USING ((auth.jwt() ->> 'email') = email OR (auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((auth.jwt() ->> 'email') = email OR (auth.jwt() ->> 'role') = 'service_role');

-- user_tracked_jobs Policies
DROP POLICY IF EXISTS "Allow user to access own tracked jobs" ON public.user_tracked_jobs;
CREATE POLICY "Allow user to access own tracked jobs"
    ON public.user_tracked_jobs FOR ALL
    USING ((auth.jwt() ->> 'email') = user_email OR (auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((auth.jwt() ->> 'email') = user_email OR (auth.jwt() ->> 'role') = 'service_role');

-- user_pipeline_runs Policies
DROP POLICY IF EXISTS "Allow user to access own pipeline runs" ON public.user_pipeline_runs;
CREATE POLICY "Allow user to access own pipeline runs"
    ON public.user_pipeline_runs FOR ALL
    USING ((auth.jwt() ->> 'email') = user_email OR (auth.jwt() ->> 'role') = 'service_role')
    WITH CHECK ((auth.jwt() ->> 'email') = user_email OR (auth.jwt() ->> 'role') = 'service_role');

-- ------------------------------------------------------------------------------
-- 7. Grant Table and Sequence Access
-- ------------------------------------------------------------------------------
GRANT ALL ON TABLE public.user_profiles TO authenticated, service_role;
GRANT ALL ON TABLE public.user_tracked_jobs TO authenticated, service_role;
GRANT ALL ON TABLE public.user_pipeline_runs TO authenticated, service_role;
GRANT ALL ON SEQUENCE public.user_tracked_jobs_id_seq TO authenticated, service_role;
GRANT ALL ON SEQUENCE public.user_pipeline_runs_id_seq TO authenticated, service_role;

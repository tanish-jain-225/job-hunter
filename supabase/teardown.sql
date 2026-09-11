-- ==============================================================================
-- 💥 Job Hunter — Complete Database Teardown & Clean-Slate Wipe
-- ==============================================================================
-- Idempotent, transaction-safe script to completely purge all Job Hunter
-- database tables, indexes, triggers, functions, and sequences from Supabase.
-- ==============================================================================

BEGIN;

-- 1. Drop all triggers explicitly first
DROP TRIGGER IF EXISTS trigger_user_tracked_jobs_updated_at ON public.user_tracked_jobs;
DROP TRIGGER IF EXISTS trigger_user_profiles_updated_at ON public.user_profiles;

-- 2. Drop all tables (CASCADE automatically drops foreign keys, indexes, and RLS policies)
DROP TABLE IF EXISTS public.user_tracked_jobs CASCADE;
DROP TABLE IF EXISTS public.user_pipeline_runs CASCADE;
DROP TABLE IF EXISTS public.user_profiles CASCADE;

-- 3. Drop sequences explicitly (ensures clean recreation on subsequent schema runs)
DROP SEQUENCE IF EXISTS public.user_tracked_jobs_id_seq CASCADE;
DROP SEQUENCE IF EXISTS public.user_pipeline_runs_id_seq CASCADE;

-- 4. Drop trigger function
DROP FUNCTION IF EXISTS public.handle_updated_at() CASCADE;

-- 5. Optional: Clean-slate wipe of registered auth users and sessions
-- ------------------------------------------------------------------------------
-- NOTE: Kept commented out by default to protect developer logins and prevent
-- accidental deletion of other apps sharing this Supabase project.
-- Uncomment the line below ONLY if you want a complete, 100% reset of all
-- auth accounts in this Supabase instance:
--
-- DELETE FROM auth.users;

COMMIT;

-- ==============================================================================
-- Done! All Job Hunter application schema and data have been completely purged.
-- You can now run `supabase/schema.sql` to cleanly re-provision the database.
-- ==============================================================================

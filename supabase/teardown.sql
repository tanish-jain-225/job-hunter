-- ==============================================================================
-- 💥 DESTROY: Job Hunter — Complete Database Teardown & Clean-Slate Wipe
-- ==============================================================================
-- WARNING: This permanently drops all Job Hunter tables, indexes, triggers,
--          and wipes all registered users and sessions from auth.users.
-- ==============================================================================

-- 1. Drop all triggers explicitly first
DROP TRIGGER IF EXISTS trigger_user_tracked_jobs_updated_at ON public.user_tracked_jobs;
DROP TRIGGER IF EXISTS trigger_user_profiles_updated_at ON public.user_profiles;

-- 2. Drop all tables (CASCADE drops foreign keys, indexes, and RLS policies)
DROP TABLE IF EXISTS public.user_tracked_jobs CASCADE;
DROP TABLE IF EXISTS public.user_pipeline_runs CASCADE;
DROP TABLE IF EXISTS public.user_profiles CASCADE;

-- 3. Drop trigger function
DROP FUNCTION IF EXISTS public.handle_updated_at() CASCADE;

-- 4. Wipe all registered auth users and active login sessions
DELETE FROM auth.users;

-- ==============================================================================
-- Done! Database is completely empty and clean.
-- ==============================================================================

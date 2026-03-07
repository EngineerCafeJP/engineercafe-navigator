-- Optimize reception table RLS policies for Issue #117
-- Replace broad FOR ALL policies with explicit CRUD policies for service_role.

-- Drop legacy FOR ALL policy and any existing granular policies on reception_sessions.
DROP POLICY IF EXISTS "Service role has full access to reception_sessions" ON reception_sessions;
DROP POLICY IF EXISTS reception_sessions_service_select ON reception_sessions;
DROP POLICY IF EXISTS reception_sessions_service_insert ON reception_sessions;
DROP POLICY IF EXISTS reception_sessions_service_update ON reception_sessions;
DROP POLICY IF EXISTS reception_sessions_service_delete ON reception_sessions;

-- Allow service_role to read reception session state for workflow orchestration.
CREATE POLICY reception_sessions_service_select ON reception_sessions
    FOR SELECT
    USING (auth.role() = 'service_role');

-- Allow service_role to create new reception session records.
CREATE POLICY reception_sessions_service_insert ON reception_sessions
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Allow service_role to advance reception session state safely.
CREATE POLICY reception_sessions_service_update ON reception_sessions
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Allow service_role to delete reception sessions for operational recovery and cleanup.
CREATE POLICY reception_sessions_service_delete ON reception_sessions
    FOR DELETE
    USING (auth.role() = 'service_role');

-- Drop legacy FOR ALL policy and any existing granular policies on visits.
DROP POLICY IF EXISTS "Service role has full access to visits" ON visits;
DROP POLICY IF EXISTS visits_service_select ON visits;
DROP POLICY IF EXISTS visits_service_insert ON visits;
DROP POLICY IF EXISTS visits_service_update ON visits;
DROP POLICY IF EXISTS visits_service_delete ON visits;

-- Allow service_role to read visit history for analytics and staff support.
CREATE POLICY visits_service_select ON visits
    FOR SELECT
    USING (auth.role() = 'service_role');

-- Allow service_role to insert visit records as reception flows begin.
CREATE POLICY visits_service_insert ON visits
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Allow service_role to update visit records as visit details change.
CREATE POLICY visits_service_update ON visits
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Allow service_role to delete visit records for safe operational cleanup.
CREATE POLICY visits_service_delete ON visits
    FOR DELETE
    USING (auth.role() = 'service_role');

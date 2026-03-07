-- Reception Flow Tables for Issue #117
-- Autonomous reception with visitor identification and visit tracking

-- Visits table: records each visit to Engineer Cafe
CREATE TABLE IF NOT EXISTS visits (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id bigint,                                    -- NULL for unregistered visitors
    session_id uuid,                                   -- Links to conversation_sessions
    visitor_id uuid,                                   -- Frontend-generated persistent ID
    purpose varchar(50) NOT NULL DEFAULT 'other',      -- facility_use, event_participation, tour, consultation, other
    purpose_detail text,                               -- Free-text detail
    visitor_type varchar(20) NOT NULL DEFAULT 'new',   -- new, returning
    started_at timestamp with time zone DEFAULT now(),
    ended_at timestamp with time zone,
    metadata jsonb DEFAULT '{}',
    created_at timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visits_user_id ON visits(user_id);
CREATE INDEX IF NOT EXISTS idx_visits_visitor_id ON visits(visitor_id);
CREATE INDEX IF NOT EXISTS idx_visits_started_at ON visits(started_at DESC);

-- Reception sessions: tracks state machine for each reception flow
CREATE TABLE IF NOT EXISTS reception_sessions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id uuid,                                   -- Links to conversation_sessions
    visitor_id uuid,                                   -- From frontend
    user_id bigint,                                    -- Resolved user (if found)
    stage varchar(30) NOT NULL DEFAULT 'initiated',    -- initiated, greeting, identifying, purpose_hearing, routing, completed, escalated
    purpose varchar(50),                               -- facility_use, event_participation, tour, consultation, other
    language varchar(5) DEFAULT 'ja',
    trigger_type varchar(30),                          -- face_detection, button_press, wake_word, nfc
    metadata jsonb DEFAULT '{}',
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reception_sessions_session_id ON reception_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_reception_sessions_visitor_id ON reception_sessions(visitor_id);

-- Enable RLS
ALTER TABLE visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE reception_sessions ENABLE ROW LEVEL SECURITY;

-- Service role access policies (matches existing pattern from init migration)
CREATE POLICY "Service role has full access to visits" ON visits
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to reception_sessions" ON reception_sessions
    FOR ALL USING (auth.role() = 'service_role');

-- Updated at trigger for reception_sessions (reuses existing function)
CREATE TRIGGER update_reception_sessions_updated_at BEFORE UPDATE
    ON reception_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

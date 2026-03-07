-- Events table for Issue #117
-- Stores event information queried by PurposeFlowService._fetch_today_events()

CREATE TABLE IF NOT EXISTS events (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    title text NOT NULL,
    name text,                                        -- Alternative title field
    event_date date,                                  -- Primary date field
    date date,                                        -- Alternative date field
    start_date date,                                  -- Alternative date field
    start_at timestamp with time zone,                -- Event start datetime
    starts_at timestamp with time zone,               -- Alternative start datetime
    start_time timestamp with time zone,              -- Alternative start time
    location text,                                    -- Event location
    venue text,                                       -- Alternative location field
    description text,
    organizer text,
    capacity integer,
    metadata jsonb DEFAULT '{}',
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_event_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_start_at ON events(start_at);

-- Enable RLS
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- Service role policies
CREATE POLICY events_service_select ON events
    FOR SELECT USING (auth.role() = 'service_role');

CREATE POLICY events_service_insert ON events
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY events_service_update ON events
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY events_service_delete ON events
    FOR DELETE USING (auth.role() = 'service_role');

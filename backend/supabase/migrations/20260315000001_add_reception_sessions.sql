-- Reception session persistence for API-backed session recovery

CREATE TABLE IF NOT EXISTS reception_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID,
    visitor_id UUID,
    user_id BIGINT,
    stage VARCHAR(30) NOT NULL DEFAULT 'initiated',
    purpose VARCHAR(50),
    language VARCHAR(5) DEFAULT 'ja',
    trigger_type VARCHAR(30),
    metadata JSONB DEFAULT '{}',
    session_data JSONB NOT NULL DEFAULT '{}',
    visitor_name TEXT,
    visitor_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

ALTER TABLE reception_sessions
    ADD COLUMN IF NOT EXISTS session_data JSONB NOT NULL DEFAULT '{}';

ALTER TABLE reception_sessions
    ADD COLUMN IF NOT EXISTS visitor_name TEXT;

ALTER TABLE reception_sessions
    ADD COLUMN IF NOT EXISTS visitor_type TEXT;

ALTER TABLE reception_sessions
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE reception_sessions
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'reception_sessions_status_check'
    ) THEN
        ALTER TABLE reception_sessions
            ADD CONSTRAINT reception_sessions_status_check
            CHECK (status IN ('active', 'completed', 'expired'));
    END IF;
END
$$;

UPDATE reception_sessions
SET
    session_data = CASE
        WHEN session_data IS NOT NULL AND session_data <> '{}'::jsonb THEN session_data
        ELSE jsonb_strip_nulls(
            jsonb_build_object(
                'id', id::text,
                'session_id', CASE WHEN session_id IS NOT NULL THEN session_id::text ELSE NULL END,
                'stage', stage,
                'language', language,
                'trigger_type', trigger_type,
                'created_at', created_at,
                'metadata', COALESCE(metadata, '{}'::jsonb),
                'purpose',
                    CASE
                        WHEN purpose IS NOT NULL
                            THEN jsonb_build_object('category', purpose)
                        ELSE NULL
                    END,
                'visitor_identity',
                    CASE
                        WHEN user_id IS NOT NULL OR visitor_type IS NOT NULL OR visitor_name IS NOT NULL THEN
                            jsonb_strip_nulls(
                                jsonb_build_object(
                                    'visitor_type',
                                        COALESCE(
                                            visitor_type,
                                            CASE
                                                WHEN user_id IS NOT NULL THEN 'returning'
                                                ELSE 'new'
                                            END
                                        ),
                                    'user_id', user_id,
                                    'name', visitor_name,
                                    'visit_count', 0
                                )
                            )
                        ELSE NULL
                    END,
                'visitor_name', visitor_name,
                'visitor_type',
                    COALESCE(
                        visitor_type,
                        CASE
                            WHEN user_id IS NOT NULL THEN 'returning'
                            ELSE NULL
                        END
                    )
            )
        )
    END,
    visitor_type = COALESCE(
        visitor_type,
        CASE
            WHEN user_id IS NOT NULL THEN 'returning'
            ELSE 'new'
        END
    ),
    status = CASE
        WHEN status = 'active' AND stage IN ('completed', 'escalated') THEN 'completed'
        ELSE status
    END,
    expires_at = COALESCE(expires_at, COALESCE(updated_at, created_at, NOW()) + INTERVAL '24 hours');

CREATE INDEX IF NOT EXISTS idx_reception_sessions_status
    ON reception_sessions(status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_reception_sessions_expires
    ON reception_sessions(expires_at)
    WHERE status = 'active';

ALTER TABLE reception_sessions ENABLE ROW LEVEL SECURITY;

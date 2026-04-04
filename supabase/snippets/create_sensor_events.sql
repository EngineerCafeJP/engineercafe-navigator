-- Sensor events table for M5Stack device trigger persistence.
-- Enables multi-instance Cloud Run deployments to share sensor state.

CREATE TABLE IF NOT EXISTS public.sensor_events (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id    text        NOT NULL,
    sensor_type  text        NOT NULL,
    distance_mm  integer     NOT NULL,
    triggered_at timestamptz NOT NULL DEFAULT now()
);

-- Fast lookup: latest event per device
CREATE INDEX IF NOT EXISTS idx_sensor_events_device_triggered
    ON public.sensor_events (device_id, triggered_at DESC);

-- Auto-cleanup safety net (application-level TTL is 30 s)
CREATE INDEX IF NOT EXISTS idx_sensor_events_triggered_at
    ON public.sensor_events (triggered_at);

-- RLS: service-role only (backend writes, backend reads)
ALTER TABLE public.sensor_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can do anything on sensor_events"
    ON public.sensor_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

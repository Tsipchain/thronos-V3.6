-- ---------------------------------------------------------------
-- TimescaleDB initialization for ThronomedICE
-- Runs automatically on first container start.
-- ---------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ---------------------------------------------------------------
-- Convert temp_readings to a TimescaleDB hypertable
-- (partitioned by timestamp - the time column)
-- ---------------------------------------------------------------
SELECT create_hypertable(
    'temp_readings',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- ---------------------------------------------------------------
-- Compression: chunks older than 7 days are compressed.
-- Typical compression ratio: 10-20x for temperature data.
-- 50GB compressed ~ 500GB-1TB of raw readings.
-- ---------------------------------------------------------------
ALTER TABLE temp_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby    = 'timestamp DESC',
    timescaledb.compress_segmentby  = 'patient_id'
);

SELECT add_compression_policy(
    'temp_readings',
    compress_after => INTERVAL '7 days'
);

-- ---------------------------------------------------------------
-- Retention: automatically drop raw readings older than 10 years.
-- Fever events (fever_events table) are kept forever.
-- ---------------------------------------------------------------
SELECT add_retention_policy(
    'temp_readings',
    drop_after => INTERVAL '10 years'
);

-- ---------------------------------------------------------------
-- Continuous Aggregate: daily fever summary per patient.
-- Pre-computed, refreshed every hour. Used by dashboards.
-- ---------------------------------------------------------------
CREATE MATERIALIZED VIEW daily_fever_summary
WITH (timescaledb.continuous) AS
SELECT
    patient_id,
    time_bucket('1 day'::interval, timestamp)    AS day,
    COUNT(*)                                      AS reading_count,
    MAX(object_temp)                              AS max_temp,
    ROUND(AVG(object_temp)::numeric, 2)           AS avg_temp,
    COUNT(*) FILTER (WHERE is_fever)              AS fever_readings,
    COUNT(*) FILTER (WHERE object_temp >= 39.0)   AS high_fever_readings
FROM temp_readings
GROUP BY patient_id, day
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'daily_fever_summary',
    start_offset      => INTERVAL '3 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- ---------------------------------------------------------------
-- Indexes for common query patterns
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_readings_patient_ts
    ON temp_readings (patient_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_readings_fever
    ON temp_readings (is_fever, timestamp DESC)
    WHERE is_fever = TRUE;

CREATE INDEX IF NOT EXISTS idx_fever_events_patient
    ON fever_events (patient_id, started_at DESC);

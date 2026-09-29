-- Confluence storage layer: TimescaleDB (PostgreSQL) with time-partitioned hypertables.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Raw readings exactly as validated from the stream (UTC)
CREATE TABLE IF NOT EXISTS raw_readings (
    ts          TIMESTAMPTZ NOT NULL,
    meter_id    TEXT        NOT NULL,
    utility     TEXT        NOT NULL CHECK (utility IN ('electricity', 'gas', 'water')),
    value       DOUBLE PRECISION,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT create_hypertable('raw_readings', 'ts', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS raw_readings_meter_ts ON raw_readings (meter_id, ts DESC);

-- Normalised readings + features + detector scores
CREATE TABLE IF NOT EXISTS processed_readings (
    ts              TIMESTAMPTZ NOT NULL,
    meter_id        TEXT        NOT NULL,
    utility         TEXT        NOT NULL,
    value           DOUBLE PRECISION,
    features        JSONB,
    scores          JSONB,
    flags           JSONB,
    ensemble_score  DOUBLE PRECISION,
    votes           SMALLINT,
    is_alert        BOOLEAN     NOT NULL DEFAULT FALSE,
    latency_ms      DOUBLE PRECISION,        -- produced_at -> decision (H2 evidence)
    PRIMARY KEY (meter_id, ts)
);
SELECT create_hypertable('processed_readings', 'ts', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS processed_utility_ts ON processed_readings (utility, ts DESC);

-- Alerts raised for operators (monitoring only: no automated actuation)
CREATE TABLE IF NOT EXISTS anomalies (
    id              BIGSERIAL,
    ts              TIMESTAMPTZ NOT NULL,
    meter_id        TEXT        NOT NULL,
    site_id         TEXT,
    utility         TEXT        NOT NULL,
    value           DOUBLE PRECISION,
    ensemble_score  DOUBLE PRECISION,
    votes           SMALLINT,
    severity        TEXT        NOT NULL DEFAULT 'info',
    explanation     JSONB,                   -- SHAP top contributions
    status          TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'dismissed', 'escalated')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('anomalies', 'ts', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- Hourly common axis for cross-utility comparison (continuous aggregate)
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_consumption
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', ts) AS hour, utility, meter_id,
       avg(value) AS avg_value, max(value) AS max_value, count(*) AS n,
       sum(is_alert::int) AS alerts
FROM processed_readings GROUP BY hour, utility, meter_id
WITH NO DATA;
SELECT add_continuous_aggregate_policy('hourly_consumption', start_offset => INTERVAL '3 days',
       end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);

-- Retention / compression (storage scalability)
ALTER TABLE raw_readings SET (timescaledb.compress, timescaledb.compress_segmentby = 'meter_id');
SELECT add_compression_policy('raw_readings', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('raw_readings', INTERVAL '400 days', if_not_exists => TRUE);

-- Audit trail: every operator action and every threshold change (ethics / accountability)
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor       TEXT        NOT NULL,
    action      TEXT        NOT NULL,        -- acknowledge | dismiss | escalate | threshold_change | view_explanation
    target      TEXT,
    details     JSONB
);

CREATE TABLE IF NOT EXISTS threshold_changes (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor       TEXT NOT NULL,
    utility     TEXT NOT NULL,
    detector    TEXT NOT NULL,
    old_value   DOUBLE PRECISION,
    new_value   DOUBLE PRECISION NOT NULL,
    reason      TEXT
);

-- Usability / trust study responses (pseudonymous participant codes only, no PII)
CREATE TABLE IF NOT EXISTS study_responses (
    id              BIGSERIAL PRIMARY KEY,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    participant     TEXT NOT NULL,
    condition       TEXT NOT NULL CHECK (condition IN ('xai', 'blackbox')),
    kind            TEXT NOT NULL,           -- task | trust | sus | tam
    item            TEXT NOT NULL,
    response        TEXT,
    correct         BOOLEAN,
    seconds         DOUBLE PRECISION
);

-- Least-privilege roles
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'confluence_ingest') THEN CREATE ROLE confluence_ingest; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'confluence_readonly') THEN CREATE ROLE confluence_readonly; END IF;
END $$;
GRANT INSERT, SELECT ON raw_readings, processed_readings, anomalies TO confluence_ingest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO confluence_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO confluence_readonly;

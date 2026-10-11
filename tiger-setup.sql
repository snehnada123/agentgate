CREATE TABLE IF NOT EXISTS agentgate_metrics(recorded_at TIMESTAMPTZ NOT NULL, requests_per_minute INTEGER NOT NULL, simulation BOOLEAN NOT NULL);
SELECT create_hypertable('agentgate_metrics','recorded_at',if_not_exists => TRUE);

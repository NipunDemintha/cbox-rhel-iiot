-- CBOX <-> RHEL tag log
CREATE TABLE IF NOT EXISTS cbox_tag_log (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    tag_name   TEXT        NOT NULL,
    value      NUMERIC,
    direction  TEXT        NOT NULL,   -- 'RHEL->CBOX' | 'CBOX->RHEL'
    raw        JSONB
);
CREATE INDEX IF NOT EXISTS idx_cbox_tag_log_ts ON cbox_tag_log (ts DESC);

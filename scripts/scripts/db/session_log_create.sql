-- AI session log table.
-- Run once: psql -U postgres -d AI_database -f session_log_create.sql
-- (or any convenient DB — this table is independent of app schema)

CREATE TABLE IF NOT EXISTS ai_session_log (
    id           SERIAL      PRIMARY KEY,
    session_date DATE        NOT NULL DEFAULT CURRENT_DATE,
    title        TEXT        NOT NULL,
    agent        TEXT        NOT NULL DEFAULT 'copilot',  -- 'copilot' | 'claude'
    issues       TEXT,                                    -- e.g. '#188, #201'
    summary      TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_log_date ON ai_session_log (session_date DESC);

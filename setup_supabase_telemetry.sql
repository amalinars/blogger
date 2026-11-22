-- ==============================================================================
-- SETUP CENTRALIZED REALTIME SERVER TELEMETRY (proxxies.bot_nodes)
-- Jalankan SEKALI di Supabase SQL Editor (aman dijalankan berulang / idempotent).
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS proxxies;

CREATE TABLE IF NOT EXISTS proxxies.bot_nodes (
    node_name      TEXT PRIMARY KEY,
    target_network TEXT NOT NULL DEFAULT 'MONETAG',
    target_url     TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'RUNNING', -- RUNNING | STOPPED
    workers_count  INT NOT NULL DEFAULT 1,
    workers_state  JSONB NOT NULL DEFAULT '[]'::jsonb,
    stats          JSONB NOT NULL DEFAULT '{}'::jsonb,
    meta           JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_nodes_heartbeat
    ON proxxies.bot_nodes (last_heartbeat DESC);

-- Pastikan event DELETE Realtime mengirim node_name lama ke UI
ALTER TABLE proxxies.bot_nodes REPLICA IDENTITY FULL;

-- Akses baca/tulis/hapus untuk monitor-ui & worker (tanpa login gate)
ALTER TABLE proxxies.bot_nodes DISABLE ROW LEVEL SECURITY;
GRANT USAGE ON SCHEMA proxxies TO anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE proxxies.bot_nodes TO anon, authenticated, service_role;

-- Daftarkan ke Supabase Realtime publication (idempotent)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')
       AND NOT EXISTS (
           SELECT 1
           FROM pg_publication_tables
           WHERE pubname = 'supabase_realtime'
             AND schemaname = 'proxxies'
             AND tablename = 'bot_nodes'
       ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE proxxies.bot_nodes;
    END IF;
END $$;

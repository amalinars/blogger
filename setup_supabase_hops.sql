-- ==============================================================================
-- HOP PROXY REGISTRY (3xK hops untuk chain GoLogin)
-- Schema: proxxies | Tabel: hop_proxy_list
--
-- Jalankan SEKALI di Supabase SQL Editor.
-- Aman dijalankan berulang (IF NOT EXISTS / CREATE OR REPLACE).
--
-- Kredensial hop disimpan di tabel ini. Akses hanya lewat RPC (SECURITY DEFINER)
-- memakai kredensial Supabase yang sama dengan proxxies.proxy_list.
-- ==============================================================================

-- 1) Tabel daftar hop
CREATE TABLE IF NOT EXISTS proxxies.hop_proxy_list (
    id BIGSERIAL PRIMARY KEY,
    host TEXT NOT NULL,
    port INT NOT NULL,
    proxy_scheme TEXT NOT NULL DEFAULT 'http',
    username TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL DEFAULT '',
    country TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT hop_proxy_list_endpoint_key UNIQUE (host, port, username)
);

CREATE INDEX IF NOT EXISTS idx_hop_proxy_list_enabled
    ON proxxies.hop_proxy_list (enabled, id);

-- 2) RLS: blokir akses tabel langsung dari anon/authenticated.
--    RPC di bawah berjalan SECURITY DEFINER (owner) sehingga tetap bisa membaca.
ALTER TABLE proxxies.hop_proxy_list ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE proxxies.hop_proxy_list FROM anon, authenticated;

-- 3) Daftar hop aktif
CREATE OR REPLACE FUNCTION proxxies.list_active_hops()
RETURNS SETOF proxxies.hop_proxy_list
LANGUAGE sql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
    SELECT *
    FROM proxxies.hop_proxy_list
    WHERE enabled = TRUE
    ORDER BY id ASC;
$$;

-- 4) Upsert batch untuk seeding dari file lokal
CREATE OR REPLACE FUNCTION proxxies.upsert_hop_proxies(p_hops JSONB)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
DECLARE
    v_count INT := 0;
BEGIN
    IF p_hops IS NULL OR jsonb_typeof(p_hops) <> 'array' THEN
        RETURN 0;
    END IF;

    INSERT INTO proxxies.hop_proxy_list (
        host, port, proxy_scheme, username, password, country, enabled
    )
    SELECT
        TRIM(elem->>'host'),
        (elem->>'port')::INT,
        COALESCE(NULLIF(TRIM(elem->>'proxy_scheme'), ''), 'http'),
        COALESCE(elem->>'username', ''),
        COALESCE(elem->>'password', ''),
        NULLIF(TRIM(elem->>'country'), ''),
        COALESCE((elem->>'enabled')::BOOLEAN, TRUE)
    FROM jsonb_array_elements(p_hops) AS elem
    WHERE COALESCE(TRIM(elem->>'host'), '') <> ''
      AND COALESCE((elem->>'port')::INT, 0) > 0
    ON CONFLICT (host, port, username) DO UPDATE
    SET proxy_scheme = EXCLUDED.proxy_scheme,
        password = EXCLUDED.password,
        country = EXCLUDED.country,
        enabled = EXCLUDED.enabled,
        updated_at = NOW();

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- 5) Grant eksekusi (pola sama dengan RPC proxy_list yang sudah ada)
GRANT EXECUTE ON FUNCTION proxxies.list_active_hops() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.upsert_hop_proxies(JSONB) TO anon, authenticated, service_role;
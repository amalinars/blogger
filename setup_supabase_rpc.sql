-- ==============================================================================
-- SETUP DISTRIBUTED MULTI-NODE PROXY COORDINATOR (ANTI RACE CONDITION)
-- Schema: proxxies | Tabel: proxy_list
-- ==============================================================================

-- 1. Tambah kolom koordinasi multi-worker & multi-node
ALTER TABLE proxxies.proxy_list 
  ADD COLUMN IF NOT EXISTS usage VARCHAR(20) DEFAULT 'IDLE',
  ADD COLUMN IF NOT EXISTS leased_by TEXT,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS target_usage JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS fail_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_error TEXT;

-- 2. Index pencarian cepat untuk high concurrency
CREATE INDEX IF NOT EXISTS idx_proxy_list_acquire 
  ON proxxies.proxy_list (health, usage, lease_expires_at);

-- 3. Stored Procedure: Atomic Acquire dengan "FOR UPDATE SKIP LOCKED"
-- Menjamin 100% TIDAK ADA DUA WORKER/NODE YANG MENDAPATKAN PROXY SAMA DI DETIK YANG SAMA!
CREATE OR REPLACE FUNCTION proxxies.acquire_proxy(
    p_caller_id TEXT,
    p_target TEXT DEFAULT 'monetag',
    p_max_uses_per_day INT DEFAULT 2,
    p_cooldown_seconds INT DEFAULT 21600,
    p_lease_seconds INT DEFAULT 600,
    p_window_seconds INT DEFAULT 86400
)
RETURNS SETOF proxxies.proxy_list
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_now_epoch BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
    v_proxy_id INT;
BEGIN
    -- Putaran 1: Cari kandidat proxy FRESH (count = 0 atau belum pernah dipakai target ini)
    -- FOR UPDATE SKIP LOCKED mengunci baris di level row database secara instan
    SELECT id INTO v_proxy_id
    FROM proxxies.proxy_list
    WHERE health = 'ALIVE'
      AND (usage = 'IDLE' OR lease_expires_at IS NULL OR lease_expires_at < NOW())
      AND (
          target_usage IS NULL 
          OR target_usage->p_target IS NULL
          OR COALESCE((target_usage->p_target->>'count')::int, 0) = 0
          OR (v_now_epoch - COALESCE((target_usage->p_target->>'last_used')::bigint, 0)) >= p_window_seconds
      )
    ORDER BY id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    -- Putaran 2: Jika stok fresh habis, ambil yang sekunder (count < max_uses & lolos cooldown)
    IF v_proxy_id IS NULL THEN
        SELECT id INTO v_proxy_id
        FROM proxxies.proxy_list
        WHERE health = 'ALIVE'
          AND (usage = 'IDLE' OR lease_expires_at IS NULL OR lease_expires_at < NOW())
          AND (
              COALESCE((target_usage->p_target->>'count')::int, 0) < p_max_uses_per_day
              AND (v_now_epoch - COALESCE((target_usage->p_target->>'last_used')::bigint, 0)) >= p_cooldown_seconds
          )
        ORDER BY COALESCE((target_usage->p_target->>'last_used')::bigint, 0) ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END IF;

    -- Kunci proxy terpilih untuk caller_id ini
    IF v_proxy_id IS NOT NULL THEN
        UPDATE proxxies.proxy_list
        SET usage = 'IN_USE',
            leased_by = p_caller_id,
            lease_expires_at = NOW() + (p_lease_seconds || ' seconds')::interval,
            updated_at = NOW()
        WHERE id = v_proxy_id;

        RETURN QUERY
        SELECT * FROM proxxies.proxy_list WHERE id = v_proxy_id;
    END IF;

    RETURN;
END;
$$;

-- 4. Stored Procedure: Release Proxy (Kembalikan status ke IDLE)
CREATE OR REPLACE FUNCTION proxxies.release_proxy(
    p_proxy_id INT,
    p_caller_id TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET usage = 'IDLE',
        leased_by = NULL,
        lease_expires_at = NULL,
        updated_at = NOW()
    WHERE id = p_proxy_id
      AND (leased_by = p_caller_id OR p_caller_id IS NULL OR usage = 'IN_USE');

    RETURN FOUND;
END;
$$;

-- 5. Stored Procedure: Record Target Hit (Update hit count & cooldown Monetag/Adsterra di Cloud)
CREATE OR REPLACE FUNCTION proxxies.record_target_hit(
    p_proxy_id INT,
    p_target TEXT,
    p_window_seconds INT DEFAULT 86400
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_now_epoch BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
    v_curr_count INT := 0;
    v_last_used BIGINT := 0;
    v_new_count INT := 1;
BEGIN
    SELECT 
        COALESCE((target_usage->p_target->>'count')::int, 0),
        COALESCE((target_usage->p_target->>'last_used')::bigint, 0)
    INTO v_curr_count, v_last_used
    FROM proxxies.proxy_list
    WHERE id = p_proxy_id;

    -- Auto-reset jika pemakaian terakhir sudah lewat dari window 24 jam
    IF v_last_used > 0 AND (v_now_epoch - v_last_used) >= p_window_seconds THEN
        v_new_count := 1;
    ELSE
        v_new_count := v_curr_count + 1;
    END IF;

    UPDATE proxxies.proxy_list
    SET target_usage = jsonb_set(
            COALESCE(target_usage, '{}'::jsonb),
            ARRAY[p_target],
            jsonb_build_object('count', v_new_count, 'last_used', v_now_epoch)
        ),
        health = CASE WHEN health = 'DEAD' THEN 'DEAD' ELSE 'ALIVE' END,
        fail_count = 0,
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 6. Stored Procedure: Report Failure (Tandai Cooldown atau Dead langsung di Cloud)
CREATE OR REPLACE FUNCTION proxxies.report_failure(
    p_proxy_id INT,
    p_error TEXT,
    p_is_fatal BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET fail_count = fail_count + 1,
        health = CASE 
            WHEN p_is_fatal OR fail_count >= 3 THEN 'DEAD' 
            ELSE 'COOLDOWN' 
        END,
        last_error = p_error,
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 7. Grant izin eksekusi ke anon, authenticated, dan service_role
GRANT EXECUTE ON FUNCTION proxxies.acquire_proxy TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.release_proxy TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.record_target_hit TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.report_failure TO anon, authenticated, service_role;

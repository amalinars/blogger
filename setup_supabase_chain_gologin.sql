-- ==============================================================================
-- MIGRASI STATE CHAIN GOLOGIN
-- Schema: proxxies | Tabel: proxy_list
--
-- Jalankan SEKALI di Supabase SQL Editor.
-- Aman dijalankan berulang (IF NOT EXISTS / CREATE OR REPLACE).
--
-- Aturan state:
--   record_probe_gologin   -> isi exit IP + latency, sehatkan (kecuali DEAD)
--   mark_cooldown_gologin  -> COOLDOWN dengan alasan jelas, TIDAK menambah fail_count
--   mark_dead_gologin      -> hanya saat IP benar-benar tidak bisa connect
--   acquire_proxy_gologin  -> revive COOLDOWN yang sudah lewat cooldown_until
-- ==============================================================================

ALTER TABLE proxxies.proxy_list
  ADD COLUMN IF NOT EXISTS ip_detected_gologin TEXT,
  ADD COLUMN IF NOT EXISTS latency_ms_gologin DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cooldown_until_gologin TIMESTAMPTZ;

-- 1) Probe sukses: isi exit IP + latency, sehatkan kalau bukan DEAD
CREATE OR REPLACE FUNCTION proxxies.record_probe_gologin(
    p_proxy_id INT,
    p_ip TEXT,
    p_latency_ms DOUBLE PRECISION
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET ip_detected_gologin = p_ip,
        latency_ms_gologin = p_latency_ms,
        last_checked_gologin = NOW(),
        health_gologin = CASE WHEN health_gologin = 'DEAD' THEN 'DEAD' ELSE 'ALIVE' END,
        cooldown_until_gologin = CASE
            WHEN health_gologin = 'DEAD' THEN cooldown_until_gologin
            ELSE NULL
        END,
        fail_count_gologin = CASE
            WHEN health_gologin = 'DEAD' THEN COALESCE(fail_count_gologin, 0)
            ELSE 0
        END,
        last_error_gologin = CASE
            WHEN health_gologin = 'DEAD' THEN last_error_gologin
            ELSE NULL
        END,
        updated_at = NOW()
    WHERE id = p_proxy_id;
    RETURN FOUND;
END;
$$;

-- 2) COOLDOWN: bukan mati, TIDAK menambah fail_count
CREATE OR REPLACE FUNCTION proxxies.mark_cooldown_gologin(
    p_proxy_id INT,
    p_reason TEXT,
    p_cooldown_seconds INT DEFAULT 900
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET health_gologin = CASE WHEN health_gologin = 'DEAD' THEN 'DEAD' ELSE 'COOLDOWN' END,
        cooldown_until_gologin = CASE
            WHEN health_gologin = 'DEAD' THEN NULL
            ELSE NOW() + (p_cooldown_seconds || ' seconds')::interval
        END,
        last_error_gologin = p_reason,
        last_checked_gologin = NOW(),
        updated_at = NOW()
    WHERE id = p_proxy_id;
    RETURN FOUND;
END;
$$;

-- 3) DEAD: hanya kalau benar-benar tidak bisa connect
CREATE OR REPLACE FUNCTION proxxies.mark_dead_gologin(
    p_proxy_id INT,
    p_reason TEXT,
    p_fatal BOOLEAN DEFAULT FALSE,
    p_cooldown_seconds INT DEFAULT 900
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
DECLARE
    v_new_fail INT;
BEGIN
    SELECT COALESCE(fail_count_gologin, 0) + 1
    INTO v_new_fail
    FROM proxxies.proxy_list
    WHERE id = p_proxy_id;

    IF v_new_fail IS NULL THEN
        RETURN FALSE;
    END IF;

    UPDATE proxxies.proxy_list
    SET fail_count_gologin = v_new_fail,
        health_gologin = CASE
            WHEN p_fatal OR v_new_fail >= 3 THEN 'DEAD'
            ELSE 'COOLDOWN'
        END,
        cooldown_until_gologin = CASE
            WHEN p_fatal OR v_new_fail >= 3 THEN NULL
            ELSE NOW() + (p_cooldown_seconds || ' seconds')::interval
        END,
        last_error_gologin = p_reason || CASE
            WHEN p_fatal OR v_new_fail >= 3 THEN ' [DEAD]'
            ELSE ' [gagal ' || v_new_fail || '/3]'
        END,
        last_checked_gologin = NOW(),
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 4) Acquire: revive COOLDOWN yang sudah lewat masa tunggu
CREATE OR REPLACE FUNCTION proxxies.acquire_proxy_gologin(
    p_caller_id TEXT,
    p_target TEXT DEFAULT 'gologin',
    p_max_uses_per_day INT DEFAULT 2,
    p_cooldown_seconds INT DEFAULT 21600,
    p_lease_seconds INT DEFAULT 600,
    p_window_seconds INT DEFAULT 86400
)
RETURNS SETOF proxxies.proxy_list
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
DECLARE
    v_now_epoch BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
    v_proxy_id INT;
BEGIN
    -- Kembalikan COOLDOWN yang sudah lewat masa tunggu ke ALIVE.
    UPDATE proxxies.proxy_list
    SET health_gologin = 'ALIVE',
        cooldown_until_gologin = NULL,
        updated_at = NOW()
    WHERE health_gologin = 'COOLDOWN'
      AND (cooldown_until_gologin IS NULL OR cooldown_until_gologin <= NOW());

    -- Putaran 1: proxy FRESH (belum pernah dipakai target ini / sudah lewat window)
    SELECT id INTO v_proxy_id
    FROM proxxies.proxy_list
    WHERE health_gologin = 'ALIVE'
      AND (usage_gologin = 'IDLE' OR lease_expires_at_gologin IS NULL OR lease_expires_at_gologin < NOW())
      AND (
          target_usage_gologin IS NULL
          OR target_usage_gologin->p_target IS NULL
          OR COALESCE((target_usage_gologin->p_target->>'count')::int, 0) = 0
          OR (v_now_epoch - COALESCE((target_usage_gologin->p_target->>'last_used')::bigint, 0)) >= p_window_seconds
      )
    ORDER BY id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    -- Putaran 2: proxy sekunder (count < max & sudah lolos cooldown)
    IF v_proxy_id IS NULL THEN
        SELECT id INTO v_proxy_id
        FROM proxxies.proxy_list
        WHERE health_gologin = 'ALIVE'
          AND (usage_gologin = 'IDLE' OR lease_expires_at_gologin IS NULL OR lease_expires_at_gologin < NOW())
          AND (
              COALESCE((target_usage_gologin->p_target->>'count')::int, 0) < p_max_uses_per_day
              AND (v_now_epoch - COALESCE((target_usage_gologin->p_target->>'last_used')::bigint, 0)) >= p_cooldown_seconds
          )
        ORDER BY COALESCE((target_usage_gologin->p_target->>'last_used')::bigint, 0) ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END IF;

    IF v_proxy_id IS NOT NULL THEN
        UPDATE proxxies.proxy_list
        SET usage_gologin = 'IN_USE',
            leased_by_gologin = p_caller_id,
            lease_expires_at_gologin = NOW() + (p_lease_seconds || ' seconds')::interval,
            updated_at = NOW()
        WHERE id = v_proxy_id;

        RETURN QUERY
        SELECT * FROM proxxies.proxy_list WHERE id = v_proxy_id;
    END IF;

    RETURN;
END;
$$;

-- 5) Hit sukses: reset fail_count + bersihkan cooldown
CREATE OR REPLACE FUNCTION proxxies.record_target_hit_gologin(
    p_proxy_id INT,
    p_target TEXT DEFAULT 'gologin',
    p_window_seconds INT DEFAULT 86400
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
DECLARE
    v_now_epoch BIGINT := EXTRACT(EPOCH FROM NOW())::BIGINT;
    v_curr_count INT := 0;
    v_last_used BIGINT := 0;
    v_new_count INT := 1;
BEGIN
    SELECT
        COALESCE((target_usage_gologin->p_target->>'count')::int, 0),
        COALESCE((target_usage_gologin->p_target->>'last_used')::bigint, 0)
    INTO v_curr_count, v_last_used
    FROM proxxies.proxy_list
    WHERE id = p_proxy_id;

    -- Reset otomatis bila window 24 jam sudah lewat
    IF v_last_used > 0 AND (v_now_epoch - v_last_used) >= p_window_seconds THEN
        v_new_count := 1;
    ELSE
        v_new_count := v_curr_count + 1;
    END IF;

    UPDATE proxxies.proxy_list
    SET target_usage_gologin = jsonb_set(
            COALESCE(target_usage_gologin, '{}'::jsonb),
            ARRAY[p_target],
            jsonb_build_object('count', v_new_count, 'last_used', v_now_epoch)
        ),
        health_gologin = CASE WHEN health_gologin = 'DEAD' THEN 'DEAD' ELSE 'ALIVE' END,
        cooldown_until_gologin = NULL,
        fail_count_gologin = 0,
        last_error_gologin = NULL,
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 6) Grant izin eksekusi
GRANT EXECUTE ON FUNCTION proxxies.record_probe_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.mark_cooldown_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.mark_dead_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.acquire_proxy_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.record_target_hit_gologin TO anon, authenticated, service_role;

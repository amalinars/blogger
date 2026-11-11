-- ==============================================================================
-- PEMISAHAN STATE PROXY GOLOGIN vs AUTOMATION
-- Schema: proxxies | Tabel: proxy_list
--
-- Jalankan file ini SEKALI di Supabase SQL Editor.
-- Setelah migrasi ini:
--   - Automation memakai kolom lama: health, usage, leased_by, target_usage, ...
--   - GoLogin memakai kolom baru : health_gologin, usage_gologin,
--                                  leased_by_gologin, target_usage_gologin, ...
-- Keduanya tidak saling mengunci / tidak saling menghabiskan kuota.
-- ==============================================================================

-- 1. Kolom koordinasi khusus GoLogin
ALTER TABLE proxxies.proxy_list
  ADD COLUMN IF NOT EXISTS usage_gologin VARCHAR(20) DEFAULT 'IDLE',
  ADD COLUMN IF NOT EXISTS health_gologin VARCHAR(20) DEFAULT 'ALIVE',
  ADD COLUMN IF NOT EXISTS leased_by_gologin TEXT,
  ADD COLUMN IF NOT EXISTS lease_expires_at_gologin TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS target_usage_gologin JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS fail_count_gologin INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_error_gologin TEXT,
  ADD COLUMN IF NOT EXISTS last_checked_gologin TIMESTAMPTZ;

-- 2. Inisialisasi baris lama (jangan menimpa hasil yang sudah ada)
UPDATE proxxies.proxy_list
SET health_gologin = COALESCE(NULLIF(health_gologin, ''), health, 'ALIVE'),
    usage_gologin = COALESCE(usage_gologin, 'IDLE'),
    target_usage_gologin = COALESCE(target_usage_gologin, '{}'::jsonb),
    fail_count_gologin = COALESCE(fail_count_gologin, 0)
WHERE health_gologin IS NULL
   OR usage_gologin IS NULL
   OR target_usage_gologin IS NULL
   OR fail_count_gologin IS NULL;

-- 3. Index acquire khusus GoLogin
CREATE INDEX IF NOT EXISTS idx_proxy_list_acquire_gologin
  ON proxxies.proxy_list (health_gologin, usage_gologin, lease_expires_at_gologin);

-- 4. Acquire atomik khusus GoLogin (FOR UPDATE SKIP LOCKED)
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

-- 5. Release khusus GoLogin
CREATE OR REPLACE FUNCTION proxxies.release_proxy_gologin(
    p_proxy_id INT,
    p_caller_id TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET usage_gologin = 'IDLE',
        leased_by_gologin = NULL,
        lease_expires_at_gologin = NULL,
        updated_at = NOW()
    WHERE id = p_proxy_id
      AND (leased_by_gologin = p_caller_id OR p_caller_id IS NULL OR usage_gologin = 'IN_USE');

    RETURN FOUND;
END;
$$;

-- 6. Catat hit target (menambah count + last_used) khusus GoLogin
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
        fail_count_gologin = 0,
        last_error_gologin = NULL,
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 7. Report failure khusus GoLogin (rotasi ke proxy lain)
CREATE OR REPLACE FUNCTION proxxies.report_failure_gologin(
    p_proxy_id INT,
    p_error TEXT,
    p_is_fatal BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
BEGIN
    UPDATE proxxies.proxy_list
    SET fail_count_gologin = COALESCE(fail_count_gologin, 0) + 1,
        health_gologin = CASE
            WHEN p_is_fatal OR (COALESCE(fail_count_gologin, 0) + 1) >= 3 THEN 'DEAD'
            ELSE 'COOLDOWN'
        END,
        last_error_gologin = p_error,
        updated_at = NOW()
    WHERE id = p_proxy_id;

    RETURN FOUND;
END;
$$;

-- 8. Reset state GoLogin (maintenance, opsional)
CREATE OR REPLACE FUNCTION proxxies.reset_gologin_state()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = proxxies, public
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE proxxies.proxy_list
    SET usage_gologin = 'IDLE',
        leased_by_gologin = NULL,
        lease_expires_at_gologin = NULL,
        health_gologin = CASE WHEN health_gologin = 'DEAD' THEN 'DEAD' ELSE 'ALIVE' END,
        fail_count_gologin = 0,
        last_error_gologin = NULL,
        target_usage_gologin = '{}'::jsonb,
        updated_at = NOW()
    WHERE id IS NOT NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- 9. Grant izin eksekusi
GRANT EXECUTE ON FUNCTION proxxies.acquire_proxy_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.release_proxy_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.record_target_hit_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.report_failure_gologin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION proxxies.reset_gologin_state TO anon, authenticated, service_role;

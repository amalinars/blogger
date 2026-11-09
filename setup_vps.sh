#!/usr/bin/env bash
# ==============================================================================
# Script Otomatis Setup Bot Ad Impression di VPS Linux (Ubuntu / Debian)
# Menyiapkan Python, Virtualenv, Dependensi GUI/Browser Camoufox, dan System Tools.
# ==============================================================================

set -e

echo -e "\033[1;36m====================================================\033[0m"
echo -e "\033[1;36m  🚀 MEMULAI SETUP BOT AD IMPRESSION DI VPS LINUX   \033[0m"
echo -e "\033[1;36m====================================================\033[0m"

# 1. Update paket sistem & install dependensi library OS (kompatibel Ubuntu 20.04/22.04/24.04+)
echo -e "\n\033[1;33m[1/5] Mengupdate sistem dan menginstall dependensi OS...\033[0m"
# Toleran terhadap mirror pihak ketiga (misal R-CRAN / PPA di Colab) yang sedang sync
sudo apt-get update -y || true
PKGS=(
    python3
    python3-pip
    python3-venv
    git
    curl
    tmux
    screen
    xvfb
    libxkbcommon-x11-0
    libgl1
    libglx-mesa0
    libegl1
    libfontconfig1
    libxrender1
    libdbus-1-3
    libnss3
    libdrm2
    libxcomposite1
    libxdamage1
    libxfixes3
    libxrandr2
    libgbm1
    libpango-1.0-0
)

# Deteksi kompatibilitas paket audio (libasound2t64 di Ubuntu 24.04+ vs libasound2 di versi lama)
if apt-cache show libasound2t64 2>/dev/null | grep -q "Package: libasound2t64"; then
    PKGS+=(libasound2t64)
elif apt-cache show libasound2 2>/dev/null | grep -q "Package: libasound2"; then
    PKGS+=(libasound2)
fi

# Deteksi kompatibilitas glib
if apt-cache show libglib2.0-0t64 2>/dev/null | grep -q "Package: libglib2.0-0t64"; then
    PKGS+=(libglib2.0-0t64)
elif apt-cache show libglib2.0-0 2>/dev/null | grep -q "Package: libglib2.0-0"; then
    PKGS+=(libglib2.0-0)
fi

# Deteksi kompatibilitas GTK-3 (wajib untuk browser Camoufox/Firefox)
if apt-cache show libgtk-3-0t64 2>/dev/null | grep -q "Package: libgtk-3-0t64"; then
    PKGS+=(libgtk-3-0t64)
elif apt-cache show libgtk-3-0 2>/dev/null | grep -q "Package: libgtk-3-0"; then
    PKGS+=(libgtk-3-0)
fi

# Dependensi tambahan Firefox
PKGS+=(libxt6 libdbus-glib-1-2)
sudo apt-get install -y --fix-missing "${PKGS[@]}" || true

# 2. Deteksi environment (Google Colab vs VPS)
IS_COLAB=false
if [ -n "$COLAB_RELEASE_TAG" ] || [ -d "/content" ] || [ -n "$COLAB_BACKEND_VERSION" ]; then
    IS_COLAB=true
fi

if [ "$IS_COLAB" = true ]; then
    echo -e "\n\033[1;36m[2/5] Terdeteksi Google Colab: Menginstall langsung ke sistem Python...\033[0m"
    echo -e "\n\033[1;33m[3/5] Menginstall library Python dari requirements.txt...\033[0m"
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo -e "\n\033[1;33m[2/5] Menyiapkan Python Virtual Environment (venv)...\033[0m"
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate

    echo -e "\n\033[1;33m[3/5] Menginstall library Python dari requirements.txt...\033[0m"
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# 4. Download binary browser Camoufox & komponen anti-detect
echo -e "\n\033[1;33m[4/5] Mengunduh dan memverifikasi browser anti-detect Camoufox...\033[0m"
python3 << 'EOF'
import sys, time

print("🔍 Memeriksa status browser Camoufox & dependensi anti-detect...")
from camoufox.pkgman import camoufox_path, CamoufoxFetcher
from camoufox.addons import DefaultAddons, maybe_download_addons
from camoufox.fpgen_model import ensure_fpgen_model
from camoufox.geolocation import (
    ALLOW_GEOIP,
    download_mmdb,
    load_geoip_config,
    save_geoip_config,
    _get_geoip_config_by_name,
    get_mmdb_path,
    needs_update,
)

# 1. Download / verifikasi binary browser dengan retry (toleran timeout/504 GitHub)
is_installed = False
try:
    p = camoufox_path(download_if_missing=False)
    print(f"  ✓ Binary browser Camoufox sudah terpasang: {p}")
    is_installed = True
except Exception:
    pass

if not is_installed:
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  ⬇️ Mengunduh binary browser Camoufox (percobaan {attempt}/{max_retries})...")
            CamoufoxFetcher().install()
            is_installed = True
            print("  ✓ Browser Camoufox berhasil dipasang.")
            break
        except Exception as e:
            print(f"  ⚠️ Percobaan {attempt} gagal ({e}).")
            if attempt < max_retries:
                time.sleep(5 * attempt)
            else:
                print("  ❌ Gagal mengunduh browser Camoufox setelah beberapa percobaan.")
                sys.exit(1)

# 2. Addon bawaan & model fpgen
try:
    print("  🧩 Memverifikasi addon browser (uBlock Origin, dll)...")
    maybe_download_addons(list(DefaultAddons))
    print("  ✓ Addon browser siap.")
except Exception as e:
    print(f"  ℹ️ Pemberitahuan addon: {e}")

try:
    print("  🧬 Memverifikasi model fingerprint generator (fpgen)...")
    ensure_fpgen_model()
    print("  ✓ Model fpgen siap.")
except Exception as e:
    print(f"  ℹ️ Pemberitahuan fpgen: {e}")

# 3. Database GeoIP (dengan fallback otomatis ke MaxMind GeoLite2 jika daijro 504 / timeout)
if ALLOW_GEOIP:
    cfg = load_geoip_config()
    ipv4 = get_mmdb_path('ipv4', cfg)
    combined = get_mmdb_path('combined', cfg) if 'combined' in cfg.get('urls', {}) else None
    has_db = (ipv4 and ipv4.exists()) or (combined and combined.exists())
    
    if not has_db or needs_update(cfg):
        print("  🌍 Menyiapkan database GeoIP anti-detect...")
        geoip_ok = False
        
        # Coba GeoIP AIO terlebih dahulu
        try:
            print("  ⬇️ Mencoba mengunduh database GeoIP AIO...")
            download_mmdb()
            geoip_ok = True
            print("  ✓ Database GeoIP AIO berhasil dipasang.")
        except Exception as e_aio:
            print(f"  ⚠️ GeoIP AIO gagal diunduh ({e_aio}).")
            print("  🔄 Mengalihkan ke database alternatif MaxMind GeoLite2...")
            try:
                g_cfg = _get_geoip_config_by_name("MaxMind GeoLite2")
                save_geoip_config(g_cfg, explicit=True)
                download_mmdb("MaxMind GeoLite2")
                geoip_ok = True
                print("  ✓ Database MaxMind GeoLite2 berhasil dipasang dan diaktifkan.")
            except Exception as e_geo:
                print(f"  ⚠️ Fallback GeoLite2 juga gagal: {e_geo}")
                
        if not geoip_ok:
            print("  ⚠️ Pemberitahuan: Database GeoIP dilewati karena server GitHub sedang timeout/504.")
            print("  ℹ️ Bot tetap dapat berjalan normal memakai fallback koordinat bawaan.")
    else:
        print("  ✓ Database GeoIP sudah tersedia.")

# 4. Smoke test verifikasi peluncuran browser
try:
    print("  🧪 Melakukan smoke test peluncuran Camoufox headless...")
    from camoufox.sync_api import Camoufox
    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        page.goto("https://example.com", timeout=25000)
        print(f"  ✅ Verifikasi berhasil! Browser aktif & responsif (Title: '{page.title()}').")
except Exception as e_smoke:
    print(f"  ⚠️ Peringatan smoke test: {e_smoke} (Akan diverifikasi kembali saat bot dijalankan)")
EOF
# 5. Beri izin eksekusi script
echo -e "\n\033[1;33m[5/5] Menyiapkan izin eksekusi file script...\033[0m"
chmod +x run_bot.py 2>/dev/null || true
chmod +x runner.sh 2>/dev/null || true

echo -e "\n\033[1;32m====================================================\033[0m"
echo -e "\033[1;32m  ✅ INSTALASI VPS SELESAI DENGAN SUKSES!            \033[0m"
echo -e "\033[1;32m====================================================\033[0m"
echo -e "Seluruh environment, dependensi OS, dan Camoufox sudah siap."
echo -e "Silakan jalankan bot secara manual kapan pun Anda siap via ./runner.sh\n"

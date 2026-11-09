#!/usr/bin/env bash
# ==============================================================================
# Script Otomatis Setup Bot Ad Impression di VPS Linux (Ubuntu / Debian)
# Menyiapkan Python, Virtualenv, Dependensi GUI/Browser Camoufox, dan System Tools.
# ==============================================================================

set -e

FORCE_FETCH=false
for arg in "$@"; do
    case "$arg" in
        --force-fetch|--update|--fetch)
            FORCE_FETCH=true
            ;;
    esac
done

echo -e "\033[1;36m====================================================\033[0m"
echo -e "\033[1;36m  🚀 MEMULAI SETUP BOT AD IMPRESSION DI VPS LINUX   \033[0m"
echo -e "\033[1;36m====================================================\033[0m"
# Deteksi hak akses sudo / root
SUDO=""
CAN_APT=false
if [ "$(id -u)" -eq 0 ]; then
    CAN_APT=true
elif command -v sudo >/dev/null 2>&1; then
    if sudo -n true 2>/dev/null; then
        SUDO="sudo"
        CAN_APT=true
    elif [ -t 0 ]; then
        SUDO="sudo"
        CAN_APT=true
    else
        echo -e "\033[1;33m⚠️ Sudo membutuhkan password di sesi non-interaktif; melewati apt-get sistem.\033[0m"
    fi
else
    echo -e "\033[1;33m⚠️ Script dijalankan sebagai non-root tanpa sudo. Instalasi paket OS dilewati.\033[0m"
fi

# 1. Update paket sistem & install dependensi library OS (kompatibel Ubuntu 20.04/22.04/24.04+)
echo -e "\n\033[1;33m[1/5] Mengupdate sistem dan menginstall dependensi OS...\033[0m"
if [ "$CAN_APT" = true ] && command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -y || true
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
    $SUDO apt-get install -y --fix-missing "${PKGS[@]}" || true
fi

# 2. Deteksi environment (Google Colab vs VPS)
IS_COLAB=false
if [ -n "$COLAB_RELEASE_TAG" ] || [ -d "/content" ] || [ -n "$COLAB_BACKEND_VERSION" ]; then
    IS_COLAB=true
fi

if [ "$IS_COLAB" = true ]; then
    echo -e "\n\033[1;36m[2/5] Terdeteksi Google Colab: Menginstall langsung ke sistem Python...\033[0m"
    echo -e "\n\033[1;33m[3/5] Menginstall library Python & Camoufox [geoip]...\033[0m"
    pip install --upgrade pip || true
    pip install -U "camoufox[geoip]"
    pip install -r requirements.txt
else
    echo -e "\n\033[1;33m[2/5] Menyiapkan Python Virtual Environment (venv)...\033[0m"
    if [ ! -d "venv" ]; then
        python3 -m venv venv || true
    fi
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi

    PIP_FLAGS=""
    if [ -z "$VIRTUAL_ENV" ]; then
        if pip install --help 2>&1 | grep -q -- "--break-system-packages"; then
            PIP_FLAGS="--break-system-packages"
        fi
    fi

    echo -e "\n\033[1;33m[3/5] Menginstall library Python & Camoufox [geoip]...\033[0m"
    pip install $PIP_FLAGS --upgrade pip || true
    pip install $PIP_FLAGS -U "camoufox[geoip]"
    pip install $PIP_FLAGS -r requirements.txt
fi

# Pastikan dependensi sistem browser Firefox/Camoufox lengkap via Playwright
if [ "$CAN_APT" = true ] && command -v python3 >/dev/null 2>&1; then
    echo -e "\n\033[1;33m[+] Memverifikasi dependensi sistem browser via Playwright...\033[0m"
    python3 -m playwright install-deps firefox >/dev/null 2>&1 || true
fi
# 4. Download binary browser Camoufox & komponen anti-detect (sesuai panduan https://camoufox.com/python/installation/)
echo -e "\n\033[1;33m[4/5] Memeriksa status browser anti-detect Camoufox & GeoIP...\033[0m"

ALREADY_INSTALLED=false
if [ "$FORCE_FETCH" = false ]; then
    if python3 -c "import sys; from camoufox.multiversion import list_installed, get_active_path; p = get_active_path(); sys.exit(0 if (list_installed() and p and p.exists()) else 1)" 2>/dev/null; then
        ALREADY_INSTALLED=true
    fi
fi

if [ "$ALREADY_INSTALLED" = true ]; then
    echo -e "  \033[1;32m✓ Binary browser Camoufox sudah terpasang dan siap digunakan.\033[0m"
    echo -e "  ℹ️ Melewati download ulang (~1.3 GB). (Jalankan './setup.sh --force-fetch' jika ingin unduh ulang)"
else
    echo -e "Menjalankan perintah resmi: \033[1;36mpython3 -m camoufox fetch\033[0m"
    echo -e "  ℹ️ Mengunduh binary browser Camoufox & dataset GeoIP (~1.3 GB)..."

    FETCH_SUCCESS=false
    MAX_RETRIES=3
    for attempt in $(seq 1 $MAX_RETRIES); do
        echo -e "  ⬇️ [Percobaan $attempt/$MAX_RETRIES] Mengambil paket dari repositori..."
        if python3 -m camoufox fetch; then
            FETCH_SUCCESS=true
            echo -e "  \033[1;32m✓ Browser Camoufox berhasil dipasang dan diperbarui.\033[0m"
            break
        else
            echo -e "  \033[1;31m⚠️ Percobaan $attempt gagal. Mencoba lagi dalam 5 detik...\033[0m"
            sleep 5
        fi
    done

    if [ "$FETCH_SUCCESS" = false ]; then
        echo -e "\033[1;31m❌ Gagal mengunduh browser Camoufox setelah $MAX_RETRIES percobaan.\033[0m"
        echo -e "Silakan cek koneksi internet ke GitHub lalu jalankan manual: python3 -m camoufox fetch"
        exit 1
    fi
fi
# Tampilkan ringkasan status package, browser, dan storage
echo -e "\n\033[1;36m📊 Informasi Versi Camoufox & Komponen Terpasang:\033[0m"
python3 -m camoufox version 2>/dev/null || true

# Smoke test verifikasi peluncuran browser
echo -e "\n\033[1;33m🧪 Menjalankan smoke test peluncuran browser Camoufox headless...\033[0m"
python3 << 'EOF'
import sys
try:
    from camoufox.sync_api import Camoufox
    print("  🚀 Meluncurkan Camoufox (headless)...")
    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        page.goto("https://example.com", timeout=30000)
        print(f"  ✅ Smoke test berhasil! Title: '{page.title()}' (URL: {page.url})")
except Exception as e:
    print(f"  ⚠️ Catatan smoke test: {e}")
    print("  ℹ️ Browser sudah terinstall; akan divalidasi ulang saat bot dijalankan.")
EOF

# 5. Beri izin eksekusi script
echo -e "\n\033[1;33m[5/5] Menyiapkan izin eksekusi file script...\033[0m"
chmod +x run_bot.py 2>/dev/null || true
chmod +x runner.sh 2>/dev/null || true
chmod +x setup_vps.sh 2>/dev/null || true
chmod +x setup.sh 2>/dev/null || true

echo -e "\n\033[1;32m====================================================\033[0m"
echo -e "\033[1;32m  ✅ INSTALASI VPS SELESAI DENGAN SUKSES!            \033[0m"
echo -e "\033[1;32m====================================================\033[0m"
echo -e "Seluruh environment, dependensi OS, dan Camoufox sudah siap."
echo -e "Silakan jalankan bot secara manual kapan pun Anda siap via ./runner.sh atau python3 run_bot.py\n"

#!/usr/bin/env bash
# ==============================================================================
# Script Otomatis Setup Bot Ad Impression (Linux VPS & Google Colab)
# Menyiapkan dependensi OS, environment Python, dan browser anti-detect Camoufox.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FORCE_FETCH=false
for arg in "$@"; do
    case "$arg" in
        --force-fetch|--update|--fetch)
            FORCE_FETCH=true
            ;;
    esac
done

# Deteksi environment (Google Colab vs Linux VPS)
IS_COLAB=false
if [ -n "${COLAB_RELEASE_TAG:-}" ] || [ -n "${COLAB_BACKEND_VERSION:-}" ] || [ -n "${COLAB_GPU:-}" ] || [ -d "/content" ]; then
    IS_COLAB=true
fi

echo -e "\033[1;36m====================================================\033[0m"
if [ "$IS_COLAB" = true ]; then
    echo -e "\033[1;36m  🚀 MEMULAI SETUP BOT AD IMPRESSION (GOOGLE COLAB) \033[0m"
else
    echo -e "\033[1;36m  🚀 MEMULAI SETUP BOT AD IMPRESSION DI VPS LINUX   \033[0m"
fi
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

is_pkg_installed() {
    dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

add_compat_pkg() {
    local t64_pkg="$1"
    local legacy_pkg="$2"
    if apt-cache show "$t64_pkg" 2>/dev/null | grep -q "Package: $t64_pkg"; then
        PKGS+=("$t64_pkg")
    elif apt-cache show "$legacy_pkg" 2>/dev/null | grep -q "Package: $legacy_pkg"; then
        PKGS+=("$legacy_pkg")
    fi
}

# 1. Update paket sistem & install dependensi OS untuk Camoufox (Ubuntu 20.04/22.04/24.04+)
echo -e "\n\033[1;33m[1/5] Memeriksa dan menginstall dependensi OS untuk Camoufox...\033[0m"
if [ "$CAN_APT" = true ] && command -v apt-get >/dev/null 2>&1; then
    # Paket inti runtime browser Camoufox (Firefox engine + X11/Xvfb)
    BASE_PKGS=(
        ca-certificates
        xvfb
        libxkbcommon-x11-0
        libgl1
        libglx-mesa0
        libegl1
        libfontconfig1
        libfreetype6
        libxrender1
        libdbus-1-3
        libdbus-glib-1-2
        libnss3
        libnspr4
        libdrm2
        libx11-6
        libx11-xcb1
        libxcb1
        libxcb-shm0
        libxcomposite1
        libxcursor1
        libxdamage1
        libxext6
        libxfixes3
        libxi6
        libxrandr2
        libgbm1
        libcairo2
        libcairo-gobject2
        libgdk-pixbuf-2.0-0
        libpango-1.0-0
        libpangocairo-1.0-0
    )

    # Paket manajemen VPS hanya diinstall di luar Google Colab
    if [ "$IS_COLAB" = false ]; then
        BASE_PKGS+=(
            python3
            python3-pip
            python3-venv
            git
            curl
            tmux
            screen
        )
    fi

    NEED_APT=false
    for pkg in "${BASE_PKGS[@]}"; do
        if ! is_pkg_installed "$pkg"; then
            NEED_APT=true
            break
        fi
    done

    if [ "$NEED_APT" = false ]; then
        for pair in "libasound2t64:libasound2" "libglib2.0-0t64:libglib2.0-0" "libgtk-3-0t64:libgtk-3-0" "libxt6t64:libxt6"; do
            t64="${pair%%:*}"
            legacy="${pair##*:}"
            if ! is_pkg_installed "$t64" && ! is_pkg_installed "$legacy"; then
                NEED_APT=true
                break
            fi
        done
    fi

    if [ "$NEED_APT" = true ]; then
        # Toleran terhadap mirror pihak ketiga (misal R-CRAN / PPA di Colab) yang sedang sync
        $SUDO apt-get update -y || true
        PKGS=("${BASE_PKGS[@]}")
        add_compat_pkg libasound2t64 libasound2
        add_compat_pkg libglib2.0-0t64 libglib2.0-0
        add_compat_pkg libgtk-3-0t64 libgtk-3-0
        add_compat_pkg libxt6t64 libxt6
        DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends --fix-missing "${PKGS[@]}" || true
    else
        echo -e "  \033[1;32m✓ Seluruh dependensi OS untuk Camoufox sudah terpasang.\033[0m"
    fi
fi

# 2. Siapkan Python environment & install package Camoufox
if [ "$IS_COLAB" = true ]; then
    echo -e "\n\033[1;36m[2/5] Terdeteksi Google Colab: Menggunakan Python environment sistem...\033[0m"
    echo -e "\n\033[1;33m[3/5] Menginstall Camoufox [geoip] dan dependensi Python...\033[0m"
    python3 -m pip install -U "camoufox[geoip]"
    python3 -m pip install -r requirements.txt
else
    echo -e "\n\033[1;33m[2/5] Menyiapkan Python Virtual Environment (venv)...\033[0m"
    if [ ! -d "venv" ]; then
        python3 -m venv venv || true
    fi
    if [ -f "venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source venv/bin/activate
    fi

    PIP_FLAGS=""
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        if python3 -m pip install --help 2>&1 | grep -q -- "--break-system-packages"; then
            PIP_FLAGS="--break-system-packages"
        fi
    fi

    echo -e "\n\033[1;33m[3/5] Menginstall Camoufox [geoip] dan dependensi Python...\033[0m"
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        python3 -m pip install --upgrade pip || true
    fi
    python3 -m pip install $PIP_FLAGS -U "camoufox[geoip]"
    python3 -m pip install $PIP_FLAGS -r requirements.txt
fi

# 4. Download binary browser Camoufox & komponen GeoIP (sesuai panduan https://camoufox.com/python/installation/)
echo -e "\n\033[1;33m[4/5] Memeriksa status browser anti-detect Camoufox & GeoIP...\033[0m"

ALREADY_INSTALLED=false
if [ "$FORCE_FETCH" = false ]; then
    if python3 -c "import sys; from camoufox.multiversion import list_installed, get_active_path; from camoufox.geolocation import ALLOW_GEOIP, get_mmdb_path; p = get_active_path(); has_bin = bool(list_installed() and p and p.exists() and ((p / 'camoufox-bin').exists() or (p / 'camoufox').exists())); has_geoip = (not ALLOW_GEOIP) or get_mmdb_path().exists(); sys.exit(0 if (has_bin and has_geoip) else 1)" 2>/dev/null; then
        ALREADY_INSTALLED=true
    fi
fi

if [ "$ALREADY_INSTALLED" = true ]; then
    echo -e "  \033[1;32m✓ Binary browser Camoufox & GeoIP sudah terpasang dan siap digunakan.\033[0m"
    echo -e "  ℹ️ Melewati download ulang (~1.3 GB). (Jalankan 'bash $(basename "$0") --force-fetch' jika ingin unduh ulang)"
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

# Verifikasi offline binary Camoufox, GeoIP, dan shared library OS
echo -e "\n\033[1;36m📊 Informasi Versi Camoufox & Verifikasi Binary:\033[0m"
python3 -m camoufox version 2>/dev/null || true
python3 - << 'EOF'
import os
import shutil
import subprocess
import sys
from camoufox.multiversion import get_active_path
from camoufox.geolocation import ALLOW_GEOIP, get_mmdb_path

active_dir = get_active_path()
if not active_dir or not active_dir.exists():
    print("  ❌ Binary browser Camoufox tidak ditemukan.")
    sys.exit(1)

print(f"  ✓ Binary Camoufox aktif : {active_dir}")
if ALLOW_GEOIP:
    mmdb = get_mmdb_path()
    if mmdb.exists():
        print(f"  ✓ Database GeoIP siap   : {mmdb}")
    else:
        print("  ⚠️ Database GeoIP belum ditemukan; akan disiapkan ulang saat dibutuhkan.")

libs_to_check = [p for p in (active_dir / "libxul.so", active_dir / "libmozgtk.so") if p.exists()]
if libs_to_check and shutil.which("ldd"):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = f"{active_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
    missing = []
    for lib in libs_to_check:
        res = subprocess.run(["ldd", str(lib)], capture_output=True, text=True, env=env)
        for line in res.stdout.splitlines():
            if "not found" in line:
                missing.append(line.strip())
    if missing:
        print("  ⚠️ Ada shared library OS yang belum terpasang:")
        for line in dict.fromkeys(missing):
            print(f"     - {line}")
    else:
        print("  ✓ Seluruh shared library OS untuk Camoufox lengkap.")
EOF

# 5. Beri izin eksekusi script
echo -e "\n\033[1;33m[5/5] Menyiapkan izin eksekusi file script...\033[0m"
chmod +x run_bot.py setup_vps.sh setup.sh 2>/dev/null || true
if [ "$IS_COLAB" = false ]; then
    chmod +x runner.sh 2>/dev/null || true
fi

echo -e "\n\033[1;32m====================================================\033[0m"
if [ "$IS_COLAB" = true ]; then
    echo -e "\033[1;32m  ✅ SETUP GOOGLE COLAB SELESAI DENGAN SUKSES!       \033[0m"
    echo -e "\033[1;32m====================================================\033[0m"
    echo -e "Environment, dependensi OS, dan Camoufox sudah siap."
    echo -e "Jalankan bot di cell Colab via: !python3 run_bot.py --target monetag --workers 1 --unlimited\n"
else
    echo -e "\033[1;32m  ✅ INSTALASI VPS SELESAI DENGAN SUKSES!            \033[0m"
    echo -e "\033[1;32m====================================================\033[0m"
    echo -e "Seluruh environment, dependensi OS, dan Camoufox sudah siap."
    echo -e "Silakan jalankan bot secara manual kapan pun Anda siap via ./runner.sh atau python3 run_bot.py\n"
fi

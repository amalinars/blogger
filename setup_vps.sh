#!/usr/bin/env bash
# ==============================================================================
# Script Otomatis Setup Bot Shortlink di VPS Linux (Ubuntu / Debian)
# Menyiapkan Python, Virtualenv, Dependensi GUI/Browser Camoufox, dan System Tools.
# ==============================================================================

set -e

echo -e "\033[1;36m====================================================\033[0m"
echo -e "\033[1;36m  🚀 MEMULAI SETUP BOT SHORTLINK DI VPS LINUX       \033[0m"
echo -e "\033[1;36m====================================================\033[0m"

# 1. Update paket sistem & install dependensi library OS (kompatibel Ubuntu 20.04/22.04/24.04+)
echo -e "\n\033[1;33m[1/5] Mengupdate sistem dan menginstall dependensi OS...\033[0m"
sudo apt update -y

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

sudo apt install -y "${PKGS[@]}"

# 2. Buat Virtual Environment Python jika belum ada
echo -e "\n\033[1;33m[2/5] Menyiapkan Python Virtual Environment (venv)...\033[0m"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 3. Upgrade pip & Install requirements Python
echo -e "\n\033[1;33m[3/5] Menginstall library Python dari requirements.txt...\033[0m"
pip install --upgrade pip
pip install -r requirements.txt

# 4. Download binary browser Camoufox
echo -e "\n\033[1;33m[4/5] Mengunduh binary browser anti-detect Camoufox...\033[0m"
camoufox fetch

# 5. Beri izin eksekusi script
echo -e "\n\033[1;33m[5/5] Menyiapkan izin eksekusi file script...\033[0m"
chmod +x run_bot.py 2>/dev/null || true
chmod +x runner.sh 2>/dev/null || true

echo -e "\n\033[1;32m====================================================\033[0m"
echo -e "\033[1;32m  ✅ INSTALASI VPS SELESAI DENGAN SUKSES!            \033[0m"
echo -e "\033[1;32m====================================================\033[0m"
echo -e "Seluruh environment, dependensi OS, dan Camoufox sudah siap."
echo -e "Silakan jalankan bot secara manual kapan pun Anda siap via ./runner.sh\n"

#!/usr/bin/env bash
# ==============================================================================
# Dynamic Tmux Runner Script untuk Bot Shortlink di Server Linux / VPS
#
# Perintah yang didukung:
#   ./runner.sh start [ARGUMEN...]  -> Jalankan bot di background tmux
#   ./runner.sh view               -> Masuk / intip live log terminal di tmux
#   ./runner.sh stop               -> Hentikan bot dan tutup session tmux
#   ./runner.sh restart            -> Restart bot di tmux
#   ./runner.sh status             -> Cek apakah bot sedang aktif berjalan
#
# Contoh pemakaian dinamis:
#   ./runner.sh start --target adsterra --workers 1 --name "⚡ Server A (Adsterra)"
#   ./runner.sh start --target monetag --workers 2 --name "💎 Server B (Monetag)"
#   ./runner.sh start --target both --workers 2
# ==============================================================================

SESSION_NAME="bot_shortlink"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Warna terminal
GREEN="\033[1;32m"
CYAN="\033[1;36m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

# Cek virtual environment
if [ -d "venv" ]; then
    RUN_PREFIX="source venv/bin/activate &&"
else
    RUN_PREFIX=""
fi

COMMAND="$1"
if [ -z "$COMMAND" ] || [[ "$COMMAND" == --* ]]; then
    # Jika parameter pertama berupa flag (misal ./runner.sh --target adsterra), anggap sebagai perintah start
    COMMAND="start"
else
    shift
fi

case "$COMMAND" in
    start)
        # Cek apakah session tmux sudah ada
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            echo -e "${YELLOW}⚠️ Session tmux '$SESSION_NAME' sudah berjalan!${RESET}"
            echo -e "Gunakan: ${CYAN}./runner.sh view${RESET} untuk melihat terminal log,"
            echo -e "atau   : ${CYAN}./runner.sh stop${RESET} untuk menghentikannya."
            exit 0
        fi

        # Parameter default jika tidak ditentukan
        PASSED_ARGS=("$@")

        has_arg() {
            local pattern="$1"
            for a in "${PASSED_ARGS[@]}"; do
                if [ "$a" = "$pattern" ]; then return 0; fi
            done
            return 1
        }

        if ! has_arg "--target"; then
            PASSED_ARGS=(--target adsterra "${PASSED_ARGS[@]}")
        fi
        if ! has_arg "--workers" && ! has_arg "-w"; then
            PASSED_ARGS=(-w 1 "${PASSED_ARGS[@]}")
        fi
        if ! has_arg "--unlimited" && ! has_arg "-u"; then
            PASSED_ARGS=(-u "${PASSED_ARGS[@]}")
        fi
        if ! has_arg "--url"; then
            PASSED_ARGS=(--url "https://article.riztama.my.id" "${PASSED_ARGS[@]}")
        fi

        ESCAPED_ARGS=""
        for arg in "${PASSED_ARGS[@]}"; do
            ESCAPED_ARGS="$ESCAPED_ARGS $(printf '%q' "$arg")"
        done

        echo -e "${CYAN}🚀 Meluncurkan bot di background session tmux: ${GREEN}$SESSION_NAME${RESET}"
        echo -e "Argumen: ${YELLOW}${PASSED_ARGS[*]}${RESET}"

        # Jalankan tmux session detached dan pertahankan window jika terjadi error awal
        tmux new-session -d -s "$SESSION_NAME" "cd '$DIR' && export PYTHONUNBUFFERED=1 && ${RUN_PREFIX} python3 -u run_bot.py $ESCAPED_ARGS; rc=\$?; if [ \$rc -ne 0 ]; then echo; echo -e '\033[1;31m[ERROR] Bot terhenti dengan kode '\$rc'. Cek penyebab di atas.\033[0m'; read -p 'Tekan Enter untuk keluar...'; fi"

        sleep 1.2
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            echo -e "${GREEN}✅ Bot BERHASIL berjalan di latar belakang!${RESET}"
            echo -e "Untuk melihat layar terminal log: ${CYAN}./runner.sh view${RESET}"
            echo -e "Untuk keluar dari tampilan tmux : Tekan ${YELLOW}Ctrl + B${RESET} lalu ${YELLOW}D${RESET}"
            echo -e "Pantau status di web dashboard : ${CYAN}https://article.riztama.my.id/monitoring${RESET}\n"
        else
            echo -e "${RED}❌ Gagal meluncurkan session tmux.${RESET}"
            echo -e "Coba jalankan perintah langsung untuk cek error:"
            echo -e "  ${CYAN}${RUN_PREFIX} python3 run_bot.py $ESCAPED_ARGS${RESET}\n"
        fi
        ;;

    view|attach|log)
        if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            echo -e "${YELLOW}⚠️ Tidak ada bot yang sedang berjalan di session '$SESSION_NAME'.${RESET}"
            echo -e "Jalankan bot dengan: ${CYAN}./runner.sh start${RESET}"
            exit 1
        fi
        echo -e "${CYAN}Menghubungkan ke session tmux '$SESSION_NAME'...${RESET}"
        echo -e "${DIM}(Untuk keluar tanpa mematikan bot: Tekan Ctrl+B lalu D)${RESET}\n"
        sleep 0.5
        tmux attach-session -t "$SESSION_NAME"
        ;;

    stop|kill)
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            echo -e "${YELLOW}Menghentikan bot di session '$SESSION_NAME'...${RESET}"
            # Kirim sinyal interrupt SIGINT (Ctrl+C) agar worker berhenti bersih
            tmux send-keys -t "$SESSION_NAME" C-c
            sleep 2
            # Hapus session tmux jika masih ada
            tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
            echo -e "${GREEN}✅ Bot berhasil dihentikan.${RESET}"
        else
            echo -e "${YELLOW}⚠️ Tidak ada session '$SESSION_NAME' yang sedang berjalan.${RESET}"
        fi
        ;;

    restart)
        echo -e "${YELLOW}Merestart bot...${RESET}"
        "$0" stop
        sleep 1
        "$0" start "$@"
        ;;

    status)
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            echo -e "${GREEN}● Bot AKTIF berjalan di background (tmux session: '$SESSION_NAME')${RESET}"
            echo -e "Gunakan: ${CYAN}./runner.sh view${RESET} untuk mengintip live log."
        else
            echo -e "${RED}○ Bot TIDAK aktif (tidak ada session tmux).${RESET}"
            echo -e "Gunakan: ${CYAN}./runner.sh start${RESET} untuk menyalakan bot."
        fi
        ;;

    *)
        echo -e "${CYAN}Penggunaan: ./runner.sh {start|view|stop|restart|status} [ARGUMEN_BOT...]${RESET}"
        echo -e "Contoh:"
        echo -e "  ./runner.sh start --target adsterra --workers 1 --name \"⚡ VPS 1\""
        echo -e "  ./runner.sh start --target monetag --workers 2 --name \"💎 VPS 2\""
        echo -e "  ./runner.sh view"
        echo -e "  ./runner.sh stop"
        ;;
esac

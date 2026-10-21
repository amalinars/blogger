import time
import re
import pytest
from automation.blog.gui import get_step_index, WorkerCard
from PySide6.QtWidgets import QApplication

# Ensure QApplication instance for widget tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_get_step_index_dwell():
    # max_pages=2, has_smartlink=True
    # Steps: Proksi (0), Beranda (1), Art 1 (2), Art 2 (3), Smartlink (4), Dwell (5), Selesai (6)
    assert get_step_index("PROXY", 1, 2, True) == 0
    assert get_step_index("LANDING", 1, 2, True) == 1
    assert get_step_index("DWELL_BERANDA", 1, 2, True) == 1
    assert get_step_index("ARTICLE", 1, 2, True) == 2
    assert get_step_index("ARTICLE", 2, 2, True) == 3
    assert get_step_index("SMARTLINK", 1, 2, True) == 4
    assert get_step_index("DWELL", 1, 2, True) == 5
    assert get_step_index("DWELL_DONE", 1, 2, True) == 5
    assert get_step_index("DONE", 1, 2, True) == 6


def test_dwell_regex_patterns():
    # Test dwell article start
    line1 = "[B1] [*] Dwell time aktif: 38s (Membaca santai & scrolling naik-turun Artikel sambil menunggu auto-refresh iklan 35s)..."
    m1 = re.search(r"(?:aktif|remaining|di Beranda|di Artikel):\s*(\d+)", line1, re.IGNORECASE)
    assert m1 is not None
    assert int(m1.group(1)) == 38
    assert "Beranda" not in line1

    # Test dwell beranda start
    line2 = "[B2] [*] Dwell time di Beranda: 20s (Membaca santai & scrolling naik-turun Beranda sambil menunggu auto-refresh iklan 35s)..."
    m2 = re.search(r"(?:aktif|remaining|di Beranda|di Artikel):\s*(\d+)", line2, re.IGNORECASE)
    assert m2 is not None
    assert int(m2.group(1)) == 20
    assert "Beranda" in line2

    # Test dwell remaining heartbeat
    line3 = "[B3] [*] ⏳ Dwell time remaining: 15s (Artikel viewability aktif)..."
    m3 = re.search(r"(?:aktif|remaining|di Beranda|di Artikel):\s*(\d+)", line3, re.IGNORECASE)
    assert m3 is not None
    assert int(m3.group(1)) == 15

    # Test smartlink ad dwell
    line4 = "[B1] [✓] [SMARTLINK] Tab iklan/smartlink terbuka (https://ad.domain). Melakukan authentic engagement di landing page (18s)..."
    m4 = re.search(r"\((\d+)s\)", line4)
    assert m4 is not None
    assert int(m4.group(1)) == 18

    # Test cooldown
    line5 = "[B4] [*] Cooling down for 7s before next session..."
    m5 = re.search(r"for\s+(\d+)s", line5)
    assert m5 is not None
    assert int(m5.group(1)) == 7


def test_worker_card_countdown(qapp):
    card = WorkerCard(worker_id=1, max_pages=2, has_smartlink=True)
    assert not card.is_dwelling
    assert card.dwell_end_time == 0.0

    # Simulate entering Dwell Time
    card.update_flow({
        "step": "DWELL",
        "status_text": "⏳ Dwell Time (30s)",
        "dwell_seconds": 30,
        "dwell_label": "Dwell Time"
    })
    assert card.is_dwelling
    assert card.dwell_end_time > time.time()
    assert "30s" in card.status_pill.text()

    # Fast forward time by simulating end time closer
    card.dwell_end_time = time.time() + 15.0
    card.tick_second()
    assert card.is_dwelling
    assert "15s" in card.status_pill.text() or "14s" in card.status_pill.text()

    # Fast forward to finished
    card.dwell_end_time = time.time() - 1.0
    card.tick_second()
    assert not card.is_dwelling
    assert "Selesai" in card.status_pill.text()

    # Reset state
    card.reset_state()
    assert not card.is_dwelling
    assert "STANDBY" in card.status_pill.text()


def test_is_target_domain():
    from automation.blog.bot import is_target_domain
    target = "https://read.riztama.my.id"

    # Valid targets
    assert is_target_domain("https://read.riztama.my.id/post/in-defense-of-deliberate-slowness", target)
    assert is_target_domain("https://read.riztama.my.id", target)
    assert is_target_domain("https://riztama.my.id/about", target)
    assert is_target_domain("about:blank", target)

    # Localhost
    assert is_target_domain("http://localhost:3000/post/test", "http://localhost:3000")
    assert is_target_domain("http://127.0.0.1:3000", "http://localhost:3000")

    # Malicious / Popunder / Ad domains must be recognized as NOT target
    assert not is_target_domain("https://chaturbate.com/?join_overlay=1&campaign=KK90V", target)
    assert not is_target_domain("https://workdeadlinededicate.com/api/users?token=123", target)
    assert not is_target_domain("https://vidox.net/MT-1495/index.php", target)
    assert not is_target_domain("https://www.betano.ca/casino/?utm_source=Adsterra", target)
    assert not is_target_domain("https://spendsdetachment.com/api/users", target)
    assert not is_target_domain("https://zoologyfibre.com/api/users", target)


def test_parse_diagnostic_resilience_lines():
    from automation.blog.gui import BotProcessWorker

    worker = BotProcessWorker([])
    logs = []
    flows = []

    worker.log_signal.connect(lambda ts, lvl, msg: logs.append((lvl, msg)))
    worker.worker_flow_signal.connect(lambda wid, data: flows.append((wid, data)))

    # Test HOLD / RECOVERY
    worker.parse_line("[B1] [!] [HOLD/RECOVERY] Halaman utama dibajak iklan! Mengembalikan layar ke blog target...")
    assert len(logs) == 1
    assert logs[0][0] == "WARN"
    assert "🔄" in logs[0][1]
    assert len(flows) == 1
    assert flows[0][1]["status_text"] == "🔄 Pemulihan Halaman..."

    # Test NAV-FALLBACK
    worker.parse_line("[B2] [*] ➡️ [NAV-FALLBACK] Navigasi langsung ke artikel blog: /post/test...")
    assert len(logs) == 2
    assert logs[1][0] == "INFO"
    assert "🧭" in logs[1][1]

    # Test Notices
    worker.parse_line("[B3] [-] [SCROLL-NOTICE] Scroll simulation notice: context destroyed")
    assert len(logs) == 3
    assert logs[2][0] == "WARN"
    assert "⚠️" in logs[2][1]

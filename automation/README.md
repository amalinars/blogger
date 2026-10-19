# Automation Suite — Chronicle Traffic & Ad Viewability Engine

Folder ini berisi bot otomasi berbasis **Python & Playwright** dengan arsitektur **Stealth Anti-Detection, Dynamic Geo-Timezone Sync, Organic Referers, dan Anti-Leak Guard** untuk memaksimalkan metrik *viewability*, *dwell time*, serta keamanan akun jaringan iklan.

---

## 📁 Struktur File
* [stealth.py](file:///home/jovan/project/botshortlink/automation/stealth.py) — Engine anti-deteksi Playwright: dynamic timezone & locale matching per negara proksi, mock `navigator.webdriver`, mock `window.chrome`, WebGL renderer & platform consistency.
* [traffic_bot.py](file:///home/jovan/project/botshortlink/automation/traffic_bot.py) — Mesin otomasi browser utama dengan weighted organic referers, authentic advertiser dwell, dan fail-safe anti-leak guard.
* [config.json](file:///home/jovan/project/botshortlink/automation/config.json) — Konfigurasi target domain, rasio referer terbobot, safe Smartlink CTR (~4%), dan durasi dwell time.
* [gui.py](file:///home/jovan/project/botshortlink/automation/gui.py) — Antarmuka visual (PySide6) dengan visualisasi status proksi, live console, dan kontrol multi-worker.
* [test_proxies.py](file:///home/jovan/project/botshortlink/automation/test_proxies.py) — Diagnostik & tes konektivitas proksi (cek hidup/mati dan latensi TCP).
* [adsterra_stats.py](file:///home/jovan/project/botshortlink/automation/adsterra_stats.py) — Pemantauan statistik API resmi (impresi, klik, CPM, revenue, breakdown negara).

---

## 🛡️ Fitur Unggulan Anti-Ban & Stealth Engine
1. **Dynamic Geolocation & Timezone Sync**: Timezone (`Intl.DateTimeFormat`), locale, dan koordinat browser secara dinamis mengikuti negara proksi (US, UK, AU, CA, FR, ID), mengeliminasi deteksi *IP-vs-Timezone Mismatch*.
2. **Weighted Organic Referer Engine**: Pintu masuk pertama mengundi referer terbobot (Google 40%, X/Twitter 15%, Reddit 10%, Bing 10%, Direct 10%, Hackernews/Medium), mengeliminasi pola *100% Direct Traffic*.
3. **Authentic Advertiser Engagement**: Klik Smartlink/Popunder tidak lagi ditutup seketika (3.5 detik). Bot melakukan dwell time 15–24 detik dengan scroll santai di landing page advertiser, mencegah tuduhan *zero-conversion click fraud*.
4. **Strict Proxy Anti-Leak Guard**: Jika seluruh proksi mati, bot **DILARANG KERAS** beralih ke koneksi lokal. Sesi langsung dibatalkan untuk melindungi IP ISP asli pengguna dari kebocoran.
5. **Corrupted Proxy Auto-Recovery**: Pemulihan otomatis jika file `proxies.json` kosong (0 byte) atau rusak.

---

## 🖥️ 1. Menjalankan Menggunakan GUI (Direkomendasikan)
Tersedia antarmuka visual (PySide6) lengkap dengan live log console, status card, dan kontrol worker:
```bash
./run_gui.sh
# atau
python3 automation/gui.py
```

---

## 💻 2. Menjalankan via Terminal / CLI

### A. Quick Test (1 Session, Terlihat di Layar)
```bash
python3 automation/traffic_bot.py --sessions 1
```

### B. Test di Server Lokal
```bash
python3 automation/traffic_bot.py --local --sessions 1
```

### C. Jalankan Headless Multi-Session
```bash
python3 automation/traffic_bot.py --headless --sessions 5 --concurrency 2
```

### D. Uji Unit Test Suite
```bash
python3 -m pytest tests/ -v
```

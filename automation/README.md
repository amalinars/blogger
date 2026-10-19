# Automation Suite — Chronicle Traffic & Ad Viewability Engine

Folder ini berisi bot otomasi berbasis **Python & Playwright** yang dirancang khusus untuk memaksimalkan metrik *viewability*, *dwell time*, dan rotasi proksi residensial sesuai panduan teknis [docs/traffic.md](../docs/traffic.md).

---

## 📁 Struktur File
* [config.json](file:///home/jovan/project/botshortlink/automation/config.json) — Konfigurasi target domain, durasi dwell time, kecepatan scroll, dan path proksi.
* [traffic_bot.py](file:///home/jovan/project/botshortlink/automation/traffic_bot.py) — Mesin otomasi browser utama (Playwright Chromium).

---

## 🚀 Cara Menjalankan

### 1. Test di Server Lokal (Headless atau GUI)
Menjalankan tes terhadap `http://localhost:3000` tanpa proksi:
```bash
python3 automation/traffic_bot.py --local --headless
```

Jika ingin melihat browser terbuka di layar (mode GUI):
```bash
python3 automation/traffic_bot.py --local
```

### 2. Jalankan terhadap Domain Produksi (`blog.riztama.my.id`)
Menggunakan proksi residensial acak dari [gologin_proxies.json](/home/jovan/project/autoview/gologin_proxies.json):
```bash
python3 automation/traffic_bot.py --headless --sessions 3
```

### 3. Targetkan Artikel Tertentu
```bash
python3 automation/traffic_bot.py --slug the-tactile-terminal-command-line-aesthetics --sessions 1
```

### 4. Pilih Proksi Tertentu Berdasarkan Indeks
```bash
# Menggunakan proksi US (indeks 0)
python3 automation/traffic_bot.py --proxy-index 0
```

---

## ⚡ Fitur Utama Engine
1. **IAB Viewability Compliance**: Melakukan scroll bertahap dengan jeda acak sehingga seluruh banner in-article dan sidebar berada di viewport minimal 1–2 detik berturut-turut.
2. **Auto-Refresh Trigger**: Bertahan di halaman (*dwell time*) selama 35–50 detik untuk memicu siklus refresh 25 detik pada banner Adsterra.
3. **Popunder First-Touch Trigger**: Melakukan simulasi sentuhan/klik di area aman untuk memicu Popunder Adsterra di detik awal.
4. **Multi-Page Navigation**: Mengklik tautan artikel internal berikutnya secara otomatis untuk menurunkan *bounce rate* dan menghasilkan header `Referer` organik.

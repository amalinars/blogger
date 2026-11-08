# Panduan Penggunaan & Manajemen Proxy (Health Check & Auto-Clean)

Dokumentasi resmi arsitektur, CLI command, dan API Python untuk pengecekan kesehatan proxy (*health check*), deteksi proxy mati (*DEAD*), serta penghapusan otomatis (*auto-delete/clean*) baik di **File Lokal (`data/proxies.json`)** maupun **Database Supabase (`proxxies.proxy_list`)**.

---

## 1. Ringkasan Cepat: Cara Cek & Hapus Sekaligus

Pengecekan dan penghapusan proxy mati dapat dilakukan langsung dengan satu baris perintah CLI menggunakan script `check_proxies.py` atau `manage_supabase_proxies.py`.

### A. Pada File Lokal (`data/proxies.json`)

```bash
# 1. Cek kesehatan seluruh proxy dan LANGSUNG HAPUS yang mati (DEAD)
python3 check_proxies.py --delete-dead

# 2. Cek dengan performa tinggi (50 thread, timeout 5 detik) dan hapus yang mati
python3 check_proxies.py --threads 50 --timeout 5 --delete-dead

# 3. Uji coba sampel dulu (misalnya 10 proxy pertama) tanpa menghapus
python3 check_proxies.py --limit 10
```

### B. Pada Cloud Database Supabase (`schema: proxxies`)

Jika bot dijalankan terdistribusi (multi-VPS / Google Colab) menggunakan Supabase sebagai database terpusat:

```bash
# Opsi 1: Lewat check_proxies.py (langsung hapus di Supabase & sinkron ke lokal)
python3 check_proxies.py --supabase --delete-dead

# Opsi 2: Lewat manage_supabase_proxies.py
python3 manage_supabase_proxies.py --delete-dead

# Opsi 3: Atur jumlah thread paralel dan timeout untuk Supabase
python3 check_proxies.py --supabase --threads 50 --timeout 5 --delete-dead
```

> **Catatan Penting:**  
> Ketika argumen `--supabase --delete-dead` dijalankan, script akan menghapus baris proxy yang mati langsung di database Supabase (REST API batch delete) dan **sekaligus membersihkan** proxy terkait di file lokal `data/proxies.json`.

## 2. Cara Kerja Health Checker & Auto-Cleaner

```
                             [ Daftar Proxy ]
                       (data/proxies.json / Supabase)
                                     │
                                     ▼
                ┌─────────────────────────────────────────┐
                │ ThreadPoolExecutor (Multi-threaded Ping) │
                │ Target: Multi-Endpoint (ipify, icanhaz) │
                └────────────────────┬────────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
             [ HTTP 200 OK ]                 [ Error / Timeout ]
             Status: ALIVE                   Status: DEAD
             Catat IP Asli & Latency         Catat Error
                     │                               │
                     │                               ▼
                     │                      Apakah flag aktif?
                     │                      --delete-dead
                     │                               │
                     │                     ┌─────────┴─────────┐
                     │                     ▼                   ▼
                     │                 [ YA ]               [ TIDAK ]
                     │            Hapus Permanen        Tandai DEAD &
                     │            dari Pool             Simpan ALIVE ke
                     │                                  proxies_alive.json
                     ▼                                         ▼
            Tetap di Pool                          Pool Tidak Berubah
```

1. **Multi-threaded Parallel Testing**: Menguji koneksi HTTP puluhan proxy secara simultan menggunakan `concurrent.futures.ThreadPoolExecutor`.
2. **IP & Latency Detection**: Mengakses endpoint pengujian IP (`http://api.ipify.org?format=json`). Jika lolos, IP eksternal terdeteksi dan latency (ms) dicatat.
3. **Penyaringan Otomatis**:
   - Jika `--delete-dead` **TIDAK** disertakan: Proxy aktif dicatat dan diekspor ke file `data/proxies_alive.json` sebagai backup cadangan.
   - Jika `--delete-dead` **DISERTAKAN**: Seluruh proxy mati segera dihapus secara atomik dari `data/proxies.json` (dan database Supabase jika flag `--supabase` digunakan).

---

## 3. Dokumentasi CLI Command Lengkap

### 3.1 Script `check_proxies.py`

Script spesialis untuk pengujian multi-threaded performa tinggi.

| Flag / Opsi | Tipe | Nilai Default | Keterangan |
| :--- | :---: | :---: | :--- |
| `--delete-dead`, `--clean` | Flag | `False` | Hapus proxy DEAD dari target. Dilengkapi Safety Guard. |
| `--force` | Flag | `False` | Bypass Safety Guard jika rasio DEAD > 35%. |
| `--supabase` | Flag | `False` | Targetkan pengecekan langsung ke tabel Supabase (`proxxies.proxy_list`). |
| `-t`, `--threads` | Integer | `20` | Jumlah thread paralel (disetel 20 agar gateway residential tidak throttled). |
| `--timeout` | Integer | `12` | Batas timeout HTTP per proxy dalam detik (default: 12s untuk residential). |
| `--retries` | Integer | `2` | Jumlah percobaan fallback endpoint sebelum menyatakan proxy DEAD. |
| `--limit` | Integer | `0` | Membatasi jumlah proxy yang diuji (`0` = uji seluruhnya). |
#### Contoh Perintah Populer:
```bash
# 1. Cek kesehatan lokal biasa (hanya inspect, tanpa hapus)
python3 check_proxies.py

# 2. Cek lokal dan bersihkan yang mati (rekomendasi sebelum bot dijalankan)
python3 check_proxies.py --delete-dead -t 50 --timeout 6

# 3. Cek seluruh database Supabase dan bersihkan yang mati
python3 check_proxies.py --supabase --delete-dead -t 60 --timeout 5

# 4. Tes cepat 20 proxy pertama di Supabase
python3 check_proxies.py --supabase --limit 20
```

---

### 3.2 Script `manage_supabase_proxies.py`

CLI terpadu untuk administrasi database proxy di Supabase.

| Flag / Opsi | Fungsi |
| :--- | :--- |
| `--test` | Uji koneksi ke endpoint Supabase & validasi skema `proxxies.proxy_list`. |
| `--list` | Tampilkan seluruh daftar proxy di Supabase beserta negara dan statusnya. |
| `--pull` | Tarik seluruh proxy dari database Supabase dan simpan ke `data/proxies.json` lokal. |
| `--check` | Jalankan health check terhadap seluruh proxy di database Supabase. |
| `--delete-dead` | Jalankan health check di Supabase dan langsung hapus baris yang berstatus `DEAD`. |
| `--reset-idle` | Kembalikan status proxy dari `IN_USE` menjadi `IDLE`. |
| `--upload "HOST:PORT:USER:PASS"` | Upload satu string proxy baru ke Supabase. |
| `--upload-file "path/file.txt"` | Upload file teks yang berisi daftar proxy baris per baris ke Supabase. |
| `-t`, `--threads` | Opsi jumlah thread (diteruskan ke checker). |
| `--timeout` | Opsi timeout detik (diteruskan ke checker). |
| `--limit` | Opsi batas jumlah proxy yang diuji (diteruskan ke checker). |

#### Contoh Penggunaan:
```bash
# Cek koneksi Supabase
python3 manage_supabase_proxies.py --test

# Tampilkan ringkasan proxy di Supabase
python3 manage_supabase_proxies.py --list

# Cek kesehatan dan bersihkan proxy mati di Supabase
python3 manage_supabase_proxies.py --delete-dead

# Tarik data terbaru dari Supabase ke file lokal
python3 manage_supabase_proxies.py --pull

# Reset status sewa proxy yang macet agar kembali IDLE
python3 manage_supabase_proxies.py --reset-idle

# Upload daftar proxy baru dari file teks
python3 manage_supabase_proxies.py --upload-file daftar_proxy.txt
```

---

## 4. Penggunaan Programmatic (Python API)

Jika Anda ingin memanggil pengecekan dan penghapusan proxy langsung dari kode Python bot Anda:

### Contoh 1: Cek & Hapus Mati Menggunakan `ProxyManager`

```python
from core.proxy_manager import ProxyManager

# Inisialisasi manager
pm = ProxyManager()

# Jalankan validasi paralel dan langsung hapus yang DEAD
# force=True akan mengabaikan cache lama dan menguji jaringan secara langsung
result = pm.test_and_delete_dead(force=True, max_workers=40)

print(f"Total Diuji    : {result['tested_total']}")
print(f"Proxy Aktif    : {result['alive']}")
print(f"Proxy Mati     : {result['dead_found']}")
print(f"Dihapus        : {result['deleted_count']}")
print(f"Sisa di Pool   : {result['remaining_total']}")
```

### Contoh 2: Pisahkan Tahap Validasi dan Hapus

```python
from core.proxy_manager import get_manager

pm = get_manager()

# 1. Validasi semua tanpa langsung menghapus
stats_val = pm.validate_all(force=True, max_workers=30)
print(f"Hasil: {stats_val['alive']} hidup, {stats_val['dead']} mati.")

# 2. Hapus yang mati jika diinginkan
if stats_val['dead'] > 0:
    deleted = pm.delete_dead_proxies()
    print(f"Berhasil menghapus {deleted} proxy DEAD.")
```

---

## 5. Struktur Konfigurasi

### File Konfigurasi Supabase (`data/supabase_config.json`)
```json
{
  "supabase_url": "https://supabase.riztama.my.id",
  "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
  "schema": "proxxies",
  "table": "proxy_list"
}
```

### Format Input Proxy yang Didukung
Sistem mengenali berbagai format proxy secara otomatis saat upload atau append:

1. **IP:Port:User:Pass**
   ```text
   geo.floppydata.com:10080:SP6xbNYIboaYTmTF:fsX1BsHD94F1pNcj
   ```
2. **User:Pass@Host:Port**
   ```text
   SP6xbNYIboaYTmTF:fsX1BsHD94F1pNcj@geo.floppydata.com:10080
   ```
3. **URL Lengkap**
   ```text
   http://SP6xbNYIboaYTmTF:fsX1BsHD94F1pNcj@geo.floppydata.com:10080
   ```
4. **IP:Port Tanpa Autentikasi**
   ```text
   192.168.1.10:8080
   ```

---

## 6. Rekomendasi & Best Practices

1. **Jalankan Sebelum Menjalankan Bot Traffic**:
   Selalu bersihkan proxy mati sebelum bot dijalankan agar session browser tidak membuang waktu mengalami *timeout* atau *connection refused*.
   ```bash
   python3 check_proxies.py --delete-dead
   ```
2. **Rekomendasi Jumlah Thread**:
   - **VPS (1-2 vCPU)**: Gunakan `--threads 20` s/d `30` agar beban CPU & RAM tetap stabil.
   - **VPS / Server Besar (4+ vCPU) atau Local PC**: Gunakan `--threads 40` s/d `60` untuk kecepatan maksimal.
3. **Timeout Pengujian**:
   - Standar residential proxy berkisar antara **5 - 7 detik** (`--timeout 6`).
   - Timeout di bawah 3 detik tidak disarankan untuk proxy residential karena waktu handshake SSL biasanya sedikit lebih lambat dari datacenter IP.

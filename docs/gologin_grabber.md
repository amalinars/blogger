# Panduan Menjalankan GoLogin Proxy Harvester (CLI & Colab)

Modul `automation/gologin_grabber.py` berfungsi untuk melakukan registrasi otomatis akun trial GoLogin menggunakan browser anti-detect Camoufox, mengambil 5 proxy residensial gratis per akun, dan langsung mengunggahnya ke database Supabase (`proxxies.proxy_list`).

---

## 🚀 Perintah Cepat (Quick Start)

### 1. Menjalankan di Local / VPS (Foreground)

```bash
# 2 worker bersamaan, mode headless, target 50 proxy
python3 automation/gologin_grabber.py --headless --workers 2 --target 50
```

### 2. Menjalankan di Google Colab (Background Runner)

```bash
# Jalankan di background
!python3 automation/gologin_grabber.py \
    --headless \
    --workers 2 \
    --unlimited \
    --skip-verifier > grabber.log 2>&1 &

# Cek live log real-time
!tail -n 50 -f grabber.log
```

---

## 📖 Mode Penggunaan

### A. Mode Target Kuota (Berhenti Saat Mencapai Jumlah Tertentu)
Jika Anda hanya butuh menambah misal **100 proxy baru**:
```bash
python3 automation/gologin_grabber.py --headless --workers 2 --target 100
```
* Worker akan otomatis berhenti begitu 100 proxy baru terkumpul di Supabase.

### B. Mode Non-Stop / Looping Terus (`--unlimited`)
Jika ingin membiarkan mesin server atau Colab terus memanen proxy tanpa batas:
```bash
python3 automation/gologin_grabber.py --headless --workers 2 --unlimited
```

### C. Menggunakan Direct IP (Tanpa Memakai Proxy yang Ada di Pool)
Secara default, grabber akan meminjam proxy dari pool untuk registrasi akun baru. Jika pool Anda kosong atau ingin menggunakan IP mesin lokal/Colab secara langsung:
```bash
python3 automation/gologin_grabber.py --headless --workers 2 --direct --skip-verifier
```

### D. Mode 1 IP 1 Proses / 1 Putaran Saja (`-r 1`)
Secara default (`-r 2`), satu IP proxy akan digunakan untuk mendaftar 2 akun berturut-turut (~10 proxy). Jika Anda ingin **1 IP hanya dipakai untuk 1 proses/akun saja** (~5 proxy lalu langsung ganti IP):
```bash
# 1 worker, 1 IP untuk 1 proses pembuatan akun GoLogin:
python3 automation/gologin_grabber.py --headless -r 1 --skip-verifier

# Mode background Colab 1 IP 1 Proses:
nohup python3 automation/gologin_grabber.py --headless --workers 1 -r 1 --unlimited --skip-verifier > grabber.log 2>&1 &
```

---

## ⚙️ Daftar Lengkap Parameter CLI

| Parameter | Deskripsi | Default |
| :--- | :--- | :--- |
| `--headless` | **Wajib di Colab/VPS**. Menjalankan browser tanpa monitor GUI. | `False` |
| `-c`, `--workers`, `--concurrency` | Jumlah browser Camoufox yang berjalan paralel. | `1` |
| `-u`, `--unlimited` | Looping terus-menerus tanpa berhenti. | `False` |
| `-t`, `--target` | Target jumlah proxy baru sebelum bot berhenti. | `100` |
| `-r`, `--rounds` | Berapa akun yang dibuat per IP sesi (1 akun = 5 proxy). | `2` (~10 proxy) |
| `--skip-verifier` | Lewati audit anti-detect (sangat disarankan di Colab/datacenter IP). | `False` |
| `--direct` | Pakai IP mesin langsung tanpa meminjam proxy dari pool. | `False` |
| `--proxy-index N` | Gunakan proxy dengan indeks nomor tertentu saja. | `None` |

---

## 💡 Tips & Rekomendasi di Google Colab

1. **Gunakan Maksimal 2 Worker (`--workers 2`)**:
   Google Colab free-tier hanya memiliki 2 core CPU. Menjalankan lebih dari 2 worker bersamaan dapat membuat CPU 100% dan memicu crash browser.
2. **Sertakan `--skip-verifier`**:
   IP bawaan Google Colab adalah IP datacenter. Menambahkan `--skip-verifier` mencegah bot tertahan saat audit browser verifier awal.
3. **Penyimpanan Otomatis**:
   Seluruh proxy hasil panen langsung tersimpan di Supabase (`proxxies.proxy_list`) dan otomatis tersinkron ke `data/proxies.json` lokal.

# Monetag Automation (CLI)

Monetag berjalan lewat `run_bot.py --target monetag`. Secara default sesi memakai
**chain proxy**: hop 3xK acak -> residential FloppyData -> browser, sama seperti
GoLogin. Jalur residential langsung tetap tersedia dengan `--no-chain`.

## Alur chain

1. Worker meminta `ChainProxyProvider.next_proxy()`.
2. Provider mengambil hop dari Supabase `proxxies.hop_proxy_list` (fallback
   `data/proxies_scrape.txt` bila ada), lalu acquire 1 residential dari pool
   `target=monetag` channel `automation` (default 2x/hari, cooldown 6 jam).
3. Provider memprobe hop dan chain penuh. Exit IP harus berasal dari residential,
   bukan hop (hop transparan dibuang). Pool Monetag juga mewajibkan endpoint
   residential mengandung `floppydata`, dan exit IP dengan flag `hosting=true`
   ditolak.
4. Browser memakai bridge lokal `127.0.0.1:<port>`.
5. Selesai sesi: sukses mencatat target hit, gagal menandai cooldown/dead sesuai
   jenis error, lalu lease residential selalu di-release.

Verifier dijalankan otomatis di mode chain. Sesi hanya digagalkan bila:
- exit IP di luar pool/ASN/ISP residential (indikasi leak), atau
- WebRTC membocorkan IP mesin.

Negara/ASN/ISP diverifikasi dengan `allow_ip_rotation=True`, jadi rotasi IP dalam
pool FloppyData yang sama tetap lolos.

## Perintah

```bash
# Default: chain aktif + verifier
python3 run_bot.py --target monetag --workers 1 --unlimited

# Tes satu kombinasi hop + residential, lalu keluar
python3 run_bot.py --target monetag --chain-test

# Fallback residential langsung (tanpa hop)
python3 run_bot.py --target monetag --no-chain

# Tuning chain
python3 run_bot.py --target monetag --hop-tries 3 --chain-timeout 15 \
  --dead-confirm-hops 2 --chain-verbose
```

Safelink (`--target safelink`) tidak memakai chain.

## Log multi-worker

Setiap baris memakai format `[HH:MM:SS] [W n] pesan`. Warna tag worker tetap
(kuning/hijau/biru/magenta/cyan bergilir), termasuk log chain, sehingga keluaran
beberapa worker yang berjalan bersamaan tetap mudah dibedakan. Tag `[Wn]` ganda
dari event worker otomatis dibersihkan.

## Konfigurasi

`automation/monetag/config.json` menyimpan default untuk pemakai non-CLI
(GUI/runner). CLI menimpa nilai berikut:

| Key | Arti |
| --- | --- |
| `use_chain` | `false` default; GUI/runner tidak terpengaruh |
| `chain_hop_tries` | jumlah hop acak per sesi |
| `chain_timeout` | timeout probe chain (detik) |
| `chain_verbose` | log detail probe |
| `chain_dead_confirm_hops` | hop gagal sebelum residential dianggap DEAD |
| `chain_hop_blacklist_seconds` | blacklist hop sementara di memori |

Limit residential mengikuti `--max-uses` dan `--cooldown`/`proxy_cooldown_hours`.

## Verifikasi impresi (iklan wajib tampil)

Sesi tidak dianggap sukses hanya karena halaman target termuat. Flow menunggu
sinyal impresi nyata:

- request serving/impression Monetag (mis. `/5/<zone>`, `/500/<zone>`,
  `/impression/<zone>`), atau
- tab popunder/popup iklan yang terbuka, atau
- overlay iklan yang terlihat (vignette / in-page push, iframe fixed ber-z-index
  tinggi).

Tag `<script data-zone>` yang sekadar termuat tidak dihitung sebagai impresi.
Jika belum ada impresi, flow:

1. menunggu `ad_wait_seconds` setelah halaman dibuka,
2. memaksa Direct Link walau `direct_link_chance` tidak kena,
3. menunggu lagi `ad_fallback_seconds` di akhir sesi.

Bila tetap tidak ada iklan yang tampil, sesi digagalkan dengan
`MonetagNoAdError` (`error_kind=no_ad`) sehingga worker merotasi proxy dan
mengulang sesi, bukan mencatat hit target. Serving domain Monetag bisa berotasi;
deteksi tetap jalan lewat zone id di URL. Setel `require_ad_impression=false`
hanya jika ingin mode lama (sesi dianggap sukses meski iklan tidak tampil).

| Key | Arti |
| --- | --- |
| `ad_hosts` | host tag/serving tambahan yang dihitung sebagai request iklan |
| `ad_zones` | zone ID Monetag yang dicari di URL request |
| `require_ad_impression` | `true` = sesi gagal bila tidak ada impresi tampil |
| `ad_wait_seconds` | batas tunggu impresi pertama setelah halaman dibuka |
| `ad_fallback_seconds` | batas tunggu impresi terakhir sebelum sesi digagalkan |


## Error dan health

- `MonetagVerificationError`: IP mismatch/leak atau WebRTC leak di mode chain.
- `MonetagProxyError`: navigasi gagal karena `ERR_PROXY_*`, `ERR_TUNNEL_*`,
  koneksi ditolak/reset, DNS, atau timeout.
- `shutdown`: error karena stop/Ctrl+C; health proxy tidak diubah.
- `cloudflare`: terdeteksi teks Cloudflare/Turnstile; proxy diberi cooldown.

Di channel `automation`, kegagalan diteruskan ke RPC `proxxies.report_failure`
(fail_count/health), sedangkan sukses mencatat `record_target_hit`.

## Troubleshooting

- **Tidak ada hop valid**: cek `proxxies.hop_proxy_list` dan `core.hop_registry`;
  jalankan `seed_hops_to_supabase.py`. Sementara bisa pakai `--no-chain`.
- **Chain test gagal**: jalankan dengan `--chain-verbose`, cek kredensial hop dan
  kuota residential `target=monetag`.
- **Verifier gagal**: lihat pesan `IP Mismatch / Proxy Leak` atau WebRTC; pastikan
  bridge hidup dan `media.peerconnection.enabled=False` terpasang di mode chain.
- **Cloudflare**: bukan bukti proxy mati; provider akan cooldown residential
  setelah kegagalan berulang.
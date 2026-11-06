#!/usr/bin/env python3
"""
sync_proxies_to_supabase.py
Script untuk mengupload seluruh 1.274 proxy dari data/proxies.json ke Supabase proxxies.proxy_list
secara batch (100 row per batch) dengan upsert (on conflict host, port, username).
"""

import json
import time
import requests

def upload_all():
    cfg = json.load(open("data/supabase_config.json"))
    url = cfg["supabase_url"].rstrip("/")
    key = cfg["supabase_key"]
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")
    data = json.load(open("data/proxies.json"))
    raw_proxies = data.get("proxies", [])
    # Deduplikasi berdasarkan (host, port, username)
    seen = set()
    proxies = []
    for p in raw_proxies:
        k = (p["host"], int(p["port"]), p.get("username", ""))
        if k not in seen:
            seen.add(k)
            proxies.append(p)

    total = len(proxies)
    print(f"📦 Ditemukan {total} proxy unik siap diupload...")

    endpoint = f"{url}/rest/v1/{table}?on_conflict=host,port,username"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    batch_size = 100
    success_count = 0

    for i in range(0, total, batch_size):
        chunk = proxies[i:i + batch_size]
        payload = []
        for p in chunk:
            payload.append({
                "host": p["host"],
                "port": int(p["port"]),
                "username": p.get("username", ""),
                "password": p.get("password", ""),
                "country": p.get("country", "US"),
                "connection_type": p.get("connection_type", "residential"),
                "health": p.get("health", "ALIVE"),
            })

        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
            if resp.status_code in (200, 201):
                success_count += len(payload)
                print(f"  [+] Batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}: Berhasil {success_count}/{total} proxy")
            else:
                print(f"  [-] Batch {i//batch_size + 1} Gagal ({resp.status_code}): {resp.text[:120]}")
                return False
        except Exception as e:
            print(f"  [-] Error koneksi: {e}")
            return False

    print(f"\n🎉 SUKSES! Total {success_count} proxy berhasil diupload ke Supabase ({schema}.{table}).")
    return True

if __name__ == "__main__":
    upload_all()

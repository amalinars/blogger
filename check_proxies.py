import json
import concurrent.futures
import requests
import time

PROXY_FILE = "data/proxies.json"
CHECK_URL = "http://api.ipify.org?format=json"
TIMEOUT = 7  # 7 detik timeout

def test_proxy(proxy_item, index):
    proxy_url = proxy_item.get("proxy_url")
    country = proxy_item.get("country", "Unknown")
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    start_time = time.time()
    try:
        response = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
        latency = round((time.time() - start_time) * 1000, 2)
        if response.status_code == 200:
            ip_detected = response.json().get("ip", "N/A")
            return {
                "index": index,
                "status": "ALIVE",
                "country": country,
                "ip": ip_detected,
                "latency_ms": latency,
                "proxy_item": proxy_item
            }
    except Exception as e:
        pass
    
    return {
        "index": index,
        "status": "DEAD",
        "country": country,
        "ip": None,
        "latency_ms": None,
        "proxy_item": proxy_item
    }

def main():
    import sys
    print(f"🔍 Membaca proxy dari {PROXY_FILE}...")
    with open(PROXY_FILE, "r") as f:
        raw_data = json.load(f)
        
    if isinstance(raw_data, dict) and "proxies" in raw_data:
        proxy_list = raw_data["proxies"]
        cursor = raw_data.get("cursor", 0)
        is_dict_format = True
    else:
        proxy_list = raw_data
        cursor = 0
        is_dict_format = False
        
    total = len(proxy_list)
    print(f"📊 Ditemukan {total} proxy. Menjalankan fast-checker multithreaded (timeout: {TIMEOUT}s)...")
    
    alive_proxies = []
    dead_proxies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(test_proxy, p, idx) for idx, p in enumerate(proxy_list, 1)]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            p_item = res["proxy_item"]
            if res["status"] == "ALIVE":
                alive_proxies.append(res)
                p_item["health"] = "ALIVE"
                p_item["ip_detected"] = res["ip"]
                p_item["latency_ms"] = res["latency_ms"]
                p_item["last_checked"] = time.time()
                p_item["fail_count"] = 0
                p_item["last_error"] = None
                print(f"  ✅ [ALIVE] Proxy #{res['index']} ({res['country']}) -> IP: {res['ip']} | Latency: {res['latency_ms']}ms")
            else:
                dead_proxies.append(res)
                p_item["health"] = "DEAD"
                p_item["last_checked"] = time.time()
                p_item["last_error"] = "Tester: Connection failed"
                
    print("\n" + "=" * 60)
    print(f"📈 HASIL PENGECEKAN PROXY:")
    print(f"   - Total Proxy  : {total}")
    print(f"   - Aktif (ALIVE): {len(alive_proxies)}")
    print(f"   - Mati (DEAD)  : {len(dead_proxies)}")
    print("=" * 60)
    
    alive_data = [item["proxy_item"] for item in alive_proxies]
    
    if "--delete-dead" in sys.argv or "--clean" in sys.argv:
        print("🗑️ Menghapus proxy DEAD dari database utama...")
        if is_dict_format:
            new_cursor = cursor % len(alive_data) if alive_data else 0
            final_data = {"cursor": new_cursor, "proxies": alive_data}
        else:
            final_data = alive_data
        with open(PROXY_FILE, "w") as f:
            json.dump(final_data, f, indent=2)
        print(f"✅ Database {PROXY_FILE} berhasil dibersihkan! Sisa {len(alive_data)} proxy aktif.")
    else:
        # Simpan proxy yang hidup ke file khusus sebagai backup
        with open("data/proxies_alive.json", "w") as f:
            json.dump(alive_data, f, indent=2)
        print(f"💾 Proxy yang masih hidup telah disimpan ke: data/proxies_alive.json")
        print("💡 Tip: Gunakan argument '--delete-dead' untuk langsung menghapus yang mati dari data/proxies.json:")
        print("   python3 check_proxies.py --delete-dead")

if __name__ == "__main__":
    main()


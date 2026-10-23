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
    print(f"🔍 Membaca proxy dari {PROXY_FILE}...")
    with open(PROXY_FILE, "r") as f:
        proxy_list = json.load(f)
        
    total = len(proxy_list)
    print(f"📊 Ditemukan {total} proxy. Menjalankan fast-checker multithreaded (timeout: {TIMEOUT}s)...")
    
    alive_proxies = []
    dead_proxies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(test_proxy, p, idx) for idx, p in enumerate(proxy_list, 1)]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res["status"] == "ALIVE":
                alive_proxies.append(res)
                print(f"  ✅ [ALIVE] Proxy #{res['index']} ({res['country']}) -> IP: {res['ip']} | Latency: {res['latency_ms']}ms")
            else:
                dead_proxies.append(res)
                
    print("\n" + "=" * 60)
    print(f"📈 HASIL PENGECEKAN PROXY:")
    print(f"   - Total Proxy: {total}")
    print(f"   - Aktif (ALIVE): {len(alive_proxies)}")
    print(f"   - Mati (DEAD)  : {len(dead_proxies)}")
    print("=" * 60)
    
    # Simpan proxy yang hidup ke file khusus
    alive_data = [item["proxy_item"] for item in alive_proxies]
    with open("data/proxies_alive.json", "w") as f:
        json.dump(alive_data, f, indent=2)
    print(f"💾 Proxy yang masih hidup telah disimpan ke: data/proxies_alive.json")

if __name__ == "__main__":
    main()

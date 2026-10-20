#!/usr/bin/env python3
"""
Adsterra Publisher Statistics Analyzer
Fetches real-time impression, CPM, CTR, and revenue data from Adsterra official API.
"""
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_api_key():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("adsterra_api_key")
        except Exception:
            pass
    return None


def fetch_stats(api_key, start_date, finish_date, group_by=None):
    url = f"https://api3.adsterratools.com/publisher/stats.json?start_date={start_date}&finish_date={finish_date}"
    if group_by:
        url += f"&group_by={group_by}"

    req = urllib.request.Request(url, headers={"X-API-Key": api_key, "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code}: {e.read().decode()}")
        return None
    except Exception as e:
        print(f"[-] Request Error: {e}")
        return None


def print_report():
    api_key = load_api_key()
    if not api_key:
        print("[-] Adsterra API Key tidak ditemukan di automation/config.json.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print("=" * 68)
    print(f"📊 LAPORAN PERFORMA IKLAN ADSTERRA (REALTIME API)")
    print(f"📅 Waktu Penarikan Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 68)

    # 1. Total Hari Ini
    data_today = fetch_stats(api_key, today, today)
    if data_today and data_today.get("items"):
        item = data_today["items"][0]
        imp = item.get("impression", 0)
        clicks = item.get("clicks", 0)
        ctr = item.get("ctr", 0.0)
        cpm = item.get("cpm", 0.0)
        rev = item.get("revenue", 0.0)
        print(f"\n🌟 TOTAL HARI INI ({today}):")
        print(f"   • Total Impresi : {imp:,}")
        print(f"   • Total Klik    : {clicks:,}")
        print(f"   • Rata-rata CTR : {ctr:.3f}%")
        print(f"   • Rata-rata CPM : ${cpm:.4f}")
        print(f"   • Pendapatan    : ${rev:.4f} (~Rp {rev * 16200:,.0f})")
    else:
        print(f"\n[-] Belum ada data agregat untuk hari ini ({today}).")

    # 2. Breakdown per Negara (Country)
    data_country = fetch_stats(api_key, today, today, group_by="country")
    if data_country and data_country.get("items"):
        print(f"\n🌍 PERFORMA PER NEGARA HARI INI:")
        print(f"   {'Negara':<10} | {'Impresi':<10} | {'Klik':<6} | {'CPM ($)':<10} | {'Revenue ($)':<12}")
        print("   " + "-" * 56)
        items = sorted(data_country["items"], key=lambda x: x.get("revenue", 0), reverse=True)
        for c in items:
            code = c.get("country", "Unknown")
            imp = c.get("impression", 0)
            clicks = c.get("clicks", 0)
            cpm = c.get("cpm", 0.0)
            rev = c.get("revenue", 0.0)
            print(f"   {code:<10} | {imp:<10,} | {clicks:<6} | ${cpm:<9.4f} | ${rev:<11.4f}")

    # 3. Breakdown per Format / Placement
    data_placement = fetch_stats(api_key, today, today, group_by="placement")
    if data_placement and data_placement.get("items"):
        print(f"\n🎯 PERFORMA PER UNIT IKLAN (PLACEMENT) HARI INI:")
        print(f"   {'Placement ID':<14} | {'Impresi':<10} | {'Klik':<6} | {'CPM ($)':<10} | {'Revenue ($)':<12}")
        print("   " + "-" * 60)
        items = sorted(data_placement["items"], key=lambda x: x.get("revenue", 0), reverse=True)
        for p in items:
            pid = str(p.get("placement", "Unknown"))
            imp = p.get("impression", 0)
            clicks = p.get("clicks", 0)
            cpm = p.get("cpm", 0.0)
            rev = p.get("revenue", 0.0)
            print(f"   {pid:<14} | {imp:<10,} | {clicks:<6} | ${cpm:<9.4f} | ${rev:<11.4f}")

    print("\n" + "=" * 68)


if __name__ == "__main__":
    print_report()

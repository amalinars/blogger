#!/usr/bin/env python3
"""
test_network.py
Diagnosa jaringan: buka target URL pakai Camoufox, tangkap semua network events
(request, response, redirect, frame navigation), bandingkan Direct IP vs Proxy.

Contoh:
    python3 test_network.py
    python3 test_network.py --url https://article.riztama.my.id/
    python3 test_network.py --proxy-only
    python3 test_network.py --direct-only
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager
from automation.youtube.camoufox_engine import create_camoufox_session, get_random_viewport

DEFAULT_URL = "https://article.riztama.my.id/"
WAIT_SECONDS = 15


def log(msg: str):
    print(msg, flush=True)


def classify_request(url: str) -> str:
    """Kategorikan request berdasarkan domain."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return "unknown"
    if "bauval.org" in host:
        return "adsterra"
    if "bstcrk.com" in host or "loopsky" in host:
        return "ad-redirect"
    if "aqml.org" in host or "staticresystems" in host or "mresystems" in host:
        return "ad-tracking"
    if "riztama.my.id" in host:
        return "own-site"
    return "external"


def capture_network(page, url: str, wait: float) -> Dict[str, Any]:
    """Navigate to url and capture all network events for `wait` seconds."""
    events: List[Dict[str, str]] = []
    navigations: List[str] = []
    redirects: List[Dict[str, str]] = []

    def on_request(request):
        events.append({
            "type": "request",
            "method": request.method,
            "url": request.url,
            "category": classify_request(request.url),
        })

    def on_response(response):
        status = response.status
        is_redirect = 300 <= status < 400
        entry = {
            "type": "response",
            "status": status,
            "url": response.url,
            "category": classify_request(response.url),
        }
        if is_redirect:
            entry["location"] = response.headers.get("location", "")
            redirects.append(entry)
        events.append(entry)

    def on_framenavigated(frame):
        if frame == page.main_frame:
            navigations.append(frame.url)

    page.on("request", on_request)
    page.on("response", on_response)
    page.main_frame.on("framenavigated", on_framenavigated)
    page.on("framenavigated", lambda frame: on_framenavigated(frame) if frame == page.main_frame else None)

    log(f"  🌐 Navigating to {url} ...")
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
    except Exception as exc:
        log(f"  ⚠️  Navigation error: {exc}")

    log(f"  ⏳ Waiting {wait}s for all ad scripts to fire ...")
    time.sleep(wait)

    # Summary
    categories: Dict[str, int] = {}
    for e in events:
        cat = e.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "final_url": page.url,
        "total_requests": len([e for e in events if e["type"] == "request"]),
        "total_responses": len([e for e in events if e["type"] == "response"]),
        "redirects": redirects,
        "main_frame_navigations": navigations,
        "category_counts": categories,
        "events": events,
    }


def print_report(label: str, report: Dict[str, Any]):
    log(f"\n{'='*70}")
    log(f"  📊 {label}")
    log(f"{'='*70}")
    log(f"  Final URL        : {report['final_url']}")
    log(f"  Total requests   : {report['total_requests']}")
    log(f"  Total responses  : {report['total_responses']}")
    log(f"  Redirects        : {len(report['redirects'])}")
    log(f"  Nav history      : {len(report['main_frame_navigations'])}")

    if report["main_frame_navigations"]:
        log("\n  📍 Main frame navigations:")
        for i, url in enumerate(report["main_frame_navigations"]):
            log(f"     {i+1}. {url[:120]}")

    if report["redirects"]:
        log("\n  🔀 HTTP Redirects (3xx):")
        for r in report["redirects"][:15]:
            log(f"     [{r['status']}] {r['url'][:100]}")
            if r.get("location"):
                log(f"           → {r['location'][:100]}")

    log("\n  📂 Request categories:")
    for cat, count in sorted(report["category_counts"].items(), key=lambda x: -x[1]):
        log(f"     {cat:20s} : {count}")

    # Highlight suspicious cross-origin navigations
    orig_host = urlparse(report["main_frame_navigations"][0]).hostname if report["main_frame_navigations"] else ""
    final_host = urlparse(report["final_url"]).hostname or ""
    if orig_host and final_host and orig_host != final_host:
        log(f"\n  🚨 REDIRECT HIJACK: {orig_host} → {final_host}")
    else:
        log(f"\n  ✅ No main-frame redirect hijack detected")


def run_direct(url: str, wait: float) -> Dict[str, Any]:
    """Test without proxy (direct IP)."""
    log("\n🔓 DIRECT IP MODE (no proxy)")
    log("-" * 50)

    with create_camoufox_session(
        proxy_data=None,
        headless=False,
        humanize=True,
        allow_ads=True,
    ) as browser:
        page = browser.new_page(viewport=get_random_viewport())
        report = capture_network(page, url, wait)
        page.close()
    return report


def run_proxy(url: str, wait: float, country: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Test with a live proxy from the pool, optionally filtered by country."""
    label = f" ({country})" if country else ""
    log(f"\n🔐 PROXY MODE{label}")
    log("-" * 50)

    pm = ProxyManager()
    caller_id = f"net_test_{int(time.time())}"
    proxy_data = pm.acquire_proxy(caller_id=caller_id, exclusive=True, verify_alive=True)
    if not proxy_data:
        log("  ❌ No alive proxy available, skipping.")
        return None

    # If country filter specified, try a few times to get matching country
    if country:
        target = country.upper()
        for _ in range(10):
            if (proxy_data.get("country") or "").upper() == target:
                break
            pm.release_proxy(proxy_data.get("id"), caller_id=caller_id)
            caller_id = f"net_test_{int(time.time())}"
            proxy_data = pm.acquire_proxy(caller_id=caller_id, exclusive=True, verify_alive=True)
            if not proxy_data:
                log(f"  ❌ No alive proxy for {country}")
                return None
        else:
            log(f"  ⚠️  Couldn't find {country} proxy, using {proxy_data.get('country')}")

    log(f"  ✅ Proxy: {proxy_data.get('country')} | {proxy_data.get('ip_detected')} | "
        f"{proxy_data.get('host')}:{proxy_data.get('port')}")

    try:
        with create_camoufox_session(
            proxy_data=proxy_data,
            headless=False,
            humanize=True,
            allow_ads=True,
        ) as browser:
            page = browser.new_page(viewport=get_random_viewport())
            report = capture_network(page, url, wait)
            page.close()
        return report
    finally:
        pm.release_proxy(proxy_data.get("id"), caller_id=caller_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Camoufox network diagnostic: direct vs proxy")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Target URL (default: {DEFAULT_URL})")
    parser.add_argument("--wait", type=float, default=WAIT_SECONDS, help=f"Wait seconds after load (default: {WAIT_SECONDS})")
    parser.add_argument("--direct-only", action="store_true", help="Only test direct IP")
    parser.add_argument("--proxy-only", action="store_true", help="Only test with proxy")
    parser.add_argument("--country", default=None, help="Filter proxy by country (e.g. UNITED STATES, FRANCE, CANADA)")
    parser.add_argument("--all-countries", action="store_true", help="Test all available countries")
    parser.add_argument("--save", action="store_true", help="Save full JSON report to data/network_report.json")
    args = parser.parse_args()

    log("🦊 CAMOUFOX NETWORK DIAGNOSTIC")
    log(f"   Target: {args.url}")
    log(f"   Wait  : {args.wait}s")

    results: Dict[str, Any] = {}

    if not args.proxy_only:
        results["direct"] = run_direct(args.url, args.wait)
        print_report("DIRECT IP", results["direct"])

    if args.all_countries:
        # Test each country in the pool
        countries = ["UNITED STATES", "FRANCE", "CANADA", "AUSTRALIA", "UNITED KINGDOM"]
        for c in countries:
            proxy_result = run_proxy(args.url, args.wait, country=c)
            if proxy_result:
                results[f"proxy_{c}"] = proxy_result
                print_report(f"PROXY: {c}", proxy_result)
    elif not args.direct_only:
        proxy_result = run_proxy(args.url, args.wait, country=args.country)
        if proxy_result:
            results["proxy"] = proxy_result
            print_report("PROXY IP", proxy_result)

    # Comparison
    if "direct" in results and "proxy" in results:
        log(f"\n{'='*70}")
        log("  ⚖️  COMPARISON")
        log(f"{'='*70}")
        d = results["direct"]
        p = results["proxy"]
        log(f"  Direct final URL : {d['final_url']}")
        log(f"  Proxy  final URL : {p['final_url']}")
        log(f"  Direct requests  : {d['total_requests']}")
        log(f"  Proxy  requests  : {p['total_requests']}")
        log(f"  Direct redirects : {len(d['redirects'])}")
        log(f"  Proxy  redirects : {len(p['redirects'])}")

        d_hijack = "🚨 YES" if urlparse(d["final_url"]).hostname != urlparse(d.get("main_frame_navigations", [""])[0] if d.get("main_frame_navigations") else "").hostname else "✅ NO"
        p_hijack = "🚨 YES" if urlparse(p["final_url"]).hostname != urlparse(p.get("main_frame_navigations", [""])[0] if p.get("main_frame_navigations") else "").hostname else "✅ NO"
        log(f"  Direct hijacked  : {d_hijack}")
        log(f"  Proxy  hijacked  : {p_hijack}")

    if args.save and results:
        out = PROJECT_ROOT / "data" / "network_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        log(f"\n  💾 Saved to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

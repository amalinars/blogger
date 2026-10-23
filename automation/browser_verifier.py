"""
Module: automation.browser_verifier
Layer 1 Core Security & Pre-Flight Verifier (Pure Assertion & Validation Engine)

Modul ini bertindak sebagai auditor/verifikator independen.
Verifier TIDAK mengatur konfigurasi proxy/OS sendiri, melainkan MENERIMA target setting
dari modul pemanggil (misal: expected_ip, expected_os, expected_country, check_ads),
lalu memvalidasi apakah browser yang sedang aktif benar-benar aman, bebas bocor (anti-leak),
dan sesuai dengan ekspektasi modul pemanggil.
"""

import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

@dataclass
class VerificationReport:
    is_safe: bool
    score: int  # 0 - 100
    match_results: Dict[str, Any] = field(default_factory=dict)
    actual_state: Dict[str, Any] = field(default_factory=dict)
    benchmarks: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konversi hasil audit ke dictionary murni untuk integrasi antar-modul."""
        return {
            "is_safe": self.is_safe,
            "score": self.score,
            "match_results": self.match_results,
            "actual_state": self.actual_state,
            "benchmarks": self.benchmarks,
            "issues": self.issues,
            "warnings": self.warnings
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialisasi hasil laporan audit ke JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def print_summary(self):
        status_icon = "🟢 PASS (AMAN & SESUAI)" if self.is_safe else "🔴 FAIL (TIDAK AMAN / MISMATCH)"
        print("\n" + "=" * 70)
        print(f"🛡️  BROWSER VERIFIER AUDIT REPORT")
        print(f"Status        : {status_icon}")
        print(f"Safety Score  : {self.score} / 100")
        print("-" * 70)

        # 1. Verification / Match Checks
        print("🎯 VALIDASI TARGET VS AKTUAL:")
        for k, v in self.match_results.items():
            if v is True:
                icon = "✅ MATCH"
            elif v is False:
                icon = "❌ MISMATCH / FAILED"
            else:
                icon = "⚪ SKIPPED"
            print(f"   - {k.replace('_', ' ').title():<22}: {icon}")

        # 2. Actual Browser State
        actual = self.actual_state
        print("\n🌐 ACTUAL BROWSER STATE:")
        print(f"   - Detected IP        : {actual.get('ip', 'Unknown')}")
        print(f"   - Country / ISP      : {actual.get('country', 'Unknown')} | {actual.get('isp', 'Unknown')}")
        print(f"   - WebRTC Leak        : {'❌ BOCOR!' if actual.get('webrtc_leak') else '✅ AMAN (Tidak Bocor)'}")
        print(f"   - Webdriver Flag     : {'❌ TRUE (Terdeteksi Bot)' if actual.get('webdriver') else '✅ FALSE / Hidden'}")
        print(f"   - Platform / OS      : {actual.get('platform', 'N/A')} ({actual.get('detected_os', 'N/A')})")
        print(f"   - WebGL GPU          : {actual.get('webgl_vendor', 'N/A')} - {actual.get('webgl_renderer', 'N/A')}")
        print(f"   - Canvas & Audio     : {'✅ Normal' if actual.get('canvas_ok') and actual.get('audio_ok') else '⚠️ Bermasalah'}")
        print(f"   - Ads Allowed        : {'✅ Normal' if actual.get('ads_allowed') else '❌ Terblokir / AdBlock'}")

        # Issues
        if self.issues:
            print("\n❌ CRITICAL ISSUES (Menyebabkan FAIL):")
            for iss in self.issues:
                print(f"   • {iss}")

        if self.warnings:
            print("\n⚠️ WARNINGS:")
            for w in self.warnings:
                print(f"   • {w}")

        print("=" * 70 + "\n")


class BrowserVerifier:
    """
    Kelas Verifier independen:
    Menerima 'page' dan target ekspektasi dari modul pemanggil,
    lalu membandingkan kondisi browser aktual dengan ekspektasi tersebut.
    """

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def verify(
        self,
        page,
        expected_ip: Optional[str] = None,
        expected_os: Optional[str] = None,
        expected_country: Optional[str] = None,
        check_ads: bool = True,
        benchmark: Optional[str] = None
    ) -> VerificationReport:
        issues = []
        warnings = []
        score = 100
        match_results = {}

        # -------------------------------------------------------------
        # 1. AUDIT IP & WEBRTC LEAK
        # -------------------------------------------------------------
        ip_data = self._inspect_network(page)
        detected_ip = ip_data.get("query")
        detected_country = ip_data.get("country", "Unknown")
        isp = ip_data.get("isp", "Unknown")
        webrtc_leak = ip_data.get("webrtc_leak", False)
        webrtc_ips = ip_data.get("webrtc_ips", [])

        # Validasi Expected IP (jika modul pemanggil mengharuskan IP tertentu / IP Proxy)
        if expected_ip:
            if not detected_ip:
                issues.append(f"Tidak dapat mendeteksi IP publik browser (Ekspektasi: {expected_ip}).")
                match_results["ip_matched"] = False
                score -= 40
            elif detected_ip != expected_ip:
                issues.append(f"IP Mismatch / Proxy Leak! Terdeteksi: {detected_ip}, padahal modul meminta: {expected_ip}")
                match_results["ip_matched"] = False
                score -= 40
            else:
                match_results["ip_matched"] = True
        else:
            match_results["ip_matched"] = None  # Direct / unspecified

        # Validasi Expected Country
        if expected_country:
            country_norm = expected_country.strip().lower()
            detected_country_norm = detected_country.strip().lower()
            country_code = ip_data.get("countryCode", "").lower()
            if country_norm in detected_country_norm or country_norm == country_code:
                match_results["country_matched"] = True
            else:
                warnings.append(f"Country Mismatch: Terdeteksi '{detected_country}', ekspektasi modul: '{expected_country}'.")
                match_results["country_matched"] = False
                score -= 10
        else:
            match_results["country_matched"] = None

        # WebRTC leak check
        if webrtc_leak:
            issues.append(f"WebRTC membocorkan IP mesin internal/asli: {webrtc_ips}")
            match_results["no_webrtc_leak"] = False
            score -= 35
        else:
            match_results["no_webrtc_leak"] = True

        # -------------------------------------------------------------
        # 2. AUDIT FINGERPRINT & STEALTH (OS, WEBDRIVER, CANVAS, AUDIO, WEBGL)
        # -------------------------------------------------------------
        fp_data = self._inspect_fingerprint(page)
        detected_platform = fp_data.get("platform", "")
        detected_ua = fp_data.get("user_agent", "")
        webdriver = fp_data.get("webdriver", False)

        # Tentukan OS aktual dari User Agent & Platform
        detected_os = "unknown"
        if "windows" in detected_ua.lower() or "win32" in detected_platform.lower() or "win64" in detected_platform.lower():
            detected_os = "windows"
        elif "mac" in detected_ua.lower() or "macintel" in detected_platform.lower():
            detected_os = "mac"
        elif "linux" in detected_ua.lower() or "linux" in detected_platform.lower():
            detected_os = "linux"

        # Validasi Expected OS
        if expected_os:
            expected_os_norm = expected_os.strip().lower()
            if detected_os == expected_os_norm:
                match_results["os_matched"] = True
            else:
                issues.append(f"OS Mismatch! Modul meminta OS '{expected_os}', namun browser terdeteksi sebagai '{detected_os}' (Platform: {detected_platform}).")
                match_results["os_matched"] = False
                score -= 25
        else:
            match_results["os_matched"] = None

        # Bot / Webdriver check
        if webdriver is True:
            issues.append("navigator.webdriver bernilai TRUE (Browser terdeteksi sebagai automasi bot).")
            match_results["stealth_passed"] = False
            score -= 40
        else:
            match_results["stealth_passed"] = True

        # WebGL renderer check
        renderer = str(fp_data.get("webgl_renderer", "")).lower()
        if "swiftshader" in renderer or "llvmpipe" in renderer or "software" in renderer:
            issues.append(f"WebGL Renderer mencurigakan (Emulasi Software VM/Bot): {fp_data.get('webgl_renderer')}")
            score -= 25

        if not fp_data.get("canvas_ok"):
            warnings.append("Canvas rendering gagal menghasilkan data atau terblokir.")
            score -= 10

        if not fp_data.get("audio_ok"):
            warnings.append("AudioContext tidak dapat diproses secara normal.")
            score -= 10

        # -------------------------------------------------------------
        # 3. AUDIT ADS RENDERING & ADBLOCK
        # -------------------------------------------------------------
        ads_data = {}
        if check_ads:
            ads_data = self._inspect_ads(page)
            if ads_data.get("adblock_detected"):
                issues.append("AdBlock terdeteksi aktif! Kontainer iklan disembunyikan/dihapus oleh browser.")
                match_results["ads_allowed"] = False
                score -= 30
            elif not ads_data.get("ads_allowed"):
                warnings.append("Kontainer elemen iklan memiliki style abnormal (mungkin terblokir sebagian).")
                match_results["ads_allowed"] = False
                score -= 15
            else:
                match_results["ads_allowed"] = True
        else:
            match_results["ads_allowed"] = None

        # -------------------------------------------------------------
        # 4. BENCHMARK EKSTERNAL (OPSIONAL)
        # -------------------------------------------------------------
        benchmarks = {}
        if benchmark:
            if benchmark in ["sannysoft", "all"]:
                benchmarks["sannysoft"] = self.audit_live_sannysoft(page)
            if benchmark in ["canvas", "all"]:
                benchmarks["canvas"] = self.audit_live_canvas(page)
            if benchmark in ["iphey", "all"]:
                benchmarks["iphey"] = self.audit_live_iphey(page)

        # Penentuan Pass / Fail
        score = max(0, min(100, score))
        is_safe = len(issues) == 0 if self.strict_mode else (score >= 60)

        actual_state = {
            "ip": detected_ip,
            "country": detected_country,
            "isp": isp,
            "webrtc_leak": webrtc_leak,
            "webrtc_ips": webrtc_ips,
            "webdriver": webdriver,
            "platform": detected_platform,
            "detected_os": detected_os,
            "user_agent": detected_ua,
            "webgl_vendor": fp_data.get("webgl_vendor"),
            "webgl_renderer": fp_data.get("webgl_renderer"),
            "canvas_ok": fp_data.get("canvas_ok"),
            "audio_ok": fp_data.get("audio_ok"),
            "plugins_ok": fp_data.get("plugins_ok"),
            "ads_allowed": ads_data.get("ads_allowed", True),
            "adblock_detected": ads_data.get("adblock_detected", False)
        }

        return VerificationReport(
            is_safe=is_safe,
            score=score,
            match_results=match_results,
            actual_state=actual_state,
            benchmarks=benchmarks,
            issues=issues,
            warnings=warnings
        )

    def _inspect_network(self, page) -> Dict[str, Any]:
        """Cek IP publik dan WebRTC leak via evaluate in-browser."""
        ip_data = {}
        try:
            ip_data = page.evaluate("""async () => {
                try {
                    const res = await fetch('http://ip-api.com/json', { signal: AbortSignal.timeout(6000) });
                    if (res.ok) return await res.json();
                } catch(e) {}
                try {
                    const res2 = await fetch('https://api.ipify.org?format=json', { signal: AbortSignal.timeout(4000) });
                    if (res2.ok) {
                        const d = await res2.json();
                        return { query: d.ip, country: 'Unknown', isp: 'Unknown' };
                    }
                } catch(e) {}
                return {};
            }""")
        except Exception:
            ip_data = {}

        detected_ip = ip_data.get("query")
        webrtc_result = {"leaked": False, "ips": []}

        try:
            webrtc_raw = page.evaluate(r"""() => {
                return new Promise((resolve) => {
                    const ips = new Set();
                    try {
                        const rtc = new RTCPeerConnection({
                            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                        });
                        rtc.createDataChannel('');
                        rtc.createOffer().then(offer => rtc.setLocalDescription(offer)).catch(() => {});
                        rtc.onicecandidate = (e) => {
                            if (!e || !e.candidate || !e.candidate.candidate) {
                                resolve(Array.from(ips));
                                return;
                            }
                            const parts = e.candidate.candidate.split(' ');
                            for (const p of parts) {
                                if (/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(p)) {
                                    if (!p.startsWith('10.') && 
                                        !p.startsWith('192.168.') && 
                                        !p.startsWith('172.') && 
                                        !p.startsWith('127.') && 
                                        !p.startsWith('0.0.') &&
                                        !p.startsWith('169.254.')) {
                                        ips.add(p);
                                    }
                                }
                            }
                        };
                        setTimeout(() => resolve(Array.from(ips)), 3000);
                    } catch(err) {
                        resolve([]);
                    }
                });
            }""")

            if webrtc_raw and detected_ip:
                leaked_ips = [ip for ip in webrtc_raw if ip != detected_ip]
                if leaked_ips:
                    webrtc_result["leaked"] = True
                    webrtc_result["ips"] = leaked_ips
            elif webrtc_raw:
                webrtc_result["ips"] = webrtc_raw
        except Exception:
            pass

        ip_data["webrtc_leak"] = webrtc_result["leaked"]
        ip_data["webrtc_ips"] = webrtc_result["ips"]
        return ip_data

    def _inspect_fingerprint(self, page) -> Dict[str, Any]:
        """Audit sidik jari (Webdriver, WebGL, Canvas, Audio, Platform, User-Agent)."""
        try:
            res = page.evaluate("""() => {
                let webglVendor = 'N/A', webglRenderer = 'N/A';
                try {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (gl) {
                        const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                        if (debugInfo) {
                            webglVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || 'N/A';
                            webglRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'N/A';
                        }
                    }
                } catch(e) {}

                let canvasOk = false;
                try {
                    const c = document.createElement('canvas');
                    c.width = 160;
                    c.height = 40;
                    const ctx = c.getContext('2d');
                    ctx.textBaseline = 'top';
                    ctx.font = '14px Arial';
                    ctx.fillStyle = '#f60';
                    ctx.fillRect(10, 10, 60, 20);
                    ctx.fillStyle = '#069';
                    ctx.fillText('AntiBotVerifier#2026', 15, 12);
                    const dataUrl = c.toDataURL();
                    canvasOk = (dataUrl && dataUrl.length > 500);
                } catch(e) {}

                let audioOk = false;
                try {
                    const AudioCtx = window.AudioContext || window.webkitAudioContext;
                    if (AudioCtx) {
                        const ctx = new AudioCtx();
                        const osc = ctx.createOscillator();
                        const analyser = ctx.createAnalyser();
                        osc.connect(analyser);
                        analyser.connect(ctx.destination);
                        audioOk = (typeof analyser.frequencyBinCount === 'number');
                        ctx.close();
                    }
                } catch(e) {}

                const pluginsCount = navigator.plugins ? navigator.plugins.length : 0;

                return {
                    webdriver: navigator.webdriver,
                    platform: navigator.platform,
                    user_agent: navigator.userAgent,
                    languages: navigator.languages,
                    webgl_vendor: webglVendor,
                    webgl_renderer: webglRenderer,
                    canvas_ok: canvasOk,
                    audio_ok: audioOk,
                    plugins_ok: (pluginsCount >= 0)
                };
            }""")
            return res
        except Exception as e:
            return {
                "webdriver": True,
                "error": str(e),
                "platform": "Error",
                "user_agent": "",
                "webgl_vendor": "Error",
                "webgl_renderer": "Error",
                "canvas_ok": False,
                "audio_ok": False,
                "plugins_ok": False
            }

    def _inspect_ads(self, page) -> Dict[str, Any]:
        """Audit apakah container iklan dan network request iklan tidak diblokir."""
        try:
            res = page.evaluate("""async () => {
                let adblockDetected = false;
                let adsAllowed = true;

                const testDiv = document.createElement('div');
                testDiv.className = 'adsbygoogle pub_300x250 pub_300x250m pub_728x90 text-ad textAd text_ad text_ads text-ads text-ad-links banner-ad ad-zone';
                testDiv.id = 'advert-banner-container';
                testDiv.style.cssText = 'width: 300px !important; height: 250px !important; position: absolute !important; left: -9999px !important; top: -9999px !important; display: block !important;';
                document.body.appendChild(testDiv);

                await new Promise(r => setTimeout(r, 60));

                const computed = window.getComputedStyle(testDiv);
                if (testDiv.offsetHeight === 0 || computed.display === 'none' || computed.visibility === 'hidden' || testDiv.offsetParent === null) {
                    adblockDetected = true;
                    adsAllowed = false;
                }
                document.body.removeChild(testDiv);

                let adNetworkReachable = false;
                try {
                    const adUrl = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js';
                    await fetch(adUrl, { method: 'HEAD', mode: 'no-cors', signal: AbortSignal.timeout(4000) });
                    adNetworkReachable = true;
                } catch(err) {
                    adNetworkReachable = false;
                }

                return {
                    adblock_detected: adblockDetected,
                    ads_allowed: adsAllowed,
                    ad_network_reachable: adNetworkReachable
                };
            }""")
            return res
        except Exception as e:
            return {
                "adblock_detected": False,
                "ads_allowed": False,
                "ad_network_reachable": False,
                "error": str(e)
            }

    def audit_live_sannysoft(self, page) -> Dict[str, Any]:
        """Audit live ke https://bot.sannysoft.com murni data/JSON."""
        results = {"passed_count": 0, "failed_count": 0, "failed_items": [], "passed_items": []}
        try:
            page.goto("https://bot.sannysoft.com", timeout=30000)
            page.wait_for_selector("#fp-table, table", timeout=15000)
            page.wait_for_timeout(1000)

            data = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll("table tr"));
                const passed = [];
                const failed = [];
                rows.forEach(r => {
                    const text = r.innerText.trim();
                    const isFailed = r.classList.contains("failed") || r.querySelector(".failed");
                    const isPassed = r.classList.contains("passed") || r.querySelector(".passed");
                    if (isFailed) failed.push(text);
                    else if (isPassed) passed.push(text);
                });
                return { passed, failed };
            }""")
            results["passed_items"] = data.get("passed", [])
            results["failed_items"] = data.get("failed", [])
            results["passed_count"] = len(results["passed_items"])
            results["failed_count"] = len(results["failed_items"])
        except Exception as e:
            results["error"] = str(e)
        return results

    def audit_live_canvas(self, page) -> Dict[str, Any]:
        """Audit live ke https://browserleaks.com/canvas murni data/JSON."""
        results = {"signature": None, "crc32": None}
        try:
            page.goto("https://browserleaks.com/canvas", timeout=30000)
            page.wait_for_selector("#crc", timeout=15000)
            page.wait_for_timeout(1000)

            data = page.evaluate("""() => {
                const crc = document.querySelector("#crc")?.innerText?.trim();
                const sig = document.querySelector("#signature")?.innerText?.trim();
                return { crc, sig };
            }""")
            results["crc32"] = data.get("crc")
            results["signature"] = data.get("sig")
        except Exception as e:
            results["error"] = str(e)
        return results

    def audit_live_iphey(self, page) -> Dict[str, Any]:
        """Audit live ke https://iphey.com murni data/JSON."""
        results = {"status": "Unknown"}
        try:
            page.goto("https://iphey.com", timeout=30000)
            page.wait_for_selector(".trust-score, .header-status, body", timeout=15000)
            page.wait_for_timeout(2500)

            text = page.text_content("body") or ""
            if "Trustworthy" in text:
                results["status"] = "Trustworthy"
            elif "Suspicious" in text:
                results["status"] = "Suspicious"
        except Exception as e:
            results["error"] = str(e)
        return results


def verify_browser(
    page,
    expected_ip: Optional[str] = None,
    expected_os: Optional[str] = None,
    expected_country: Optional[str] = None,
    check_ads: bool = True,
    strict_mode: bool = True,
    benchmark: Optional[str] = None
) -> VerificationReport:
    """
    Fungsi utama (Gatekeeper Entrypoint) yang dipanggil oleh modul lain.
    Menerima 'page' dan setting ekspektasi dari modul pemanggil:
    
    Contoh:
        report = verify_browser(
            page,
            expected_ip="88.188.63.213",
            expected_os="windows",
            check_ads=True
        )
        if not report.is_safe:
            print("Gagal audit:", report.issues)
            return False
    """
    verifier = BrowserVerifier(strict_mode=strict_mode)
    report = verifier.verify(
        page,
        expected_ip=expected_ip,
        expected_os=expected_os,
        expected_country=expected_country,
        check_ads=check_ads,
        benchmark=benchmark
    )
    return report


if __name__ == "__main__":
    import argparse
    from camoufox.sync_api import Camoufox

    parser = argparse.ArgumentParser(description="Core Browser & IP Verifier (Pure Assertion Engine)")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless")
    parser.add_argument("--expected-ip", type=str, default=None, help="IP yang diharapkan muncul (validasi leak)")
    parser.add_argument("--expected-os", type=str, default="windows", help="OS yang diharapkan (windows, mac, linux)")
    parser.add_argument("--expected-country", type=str, default=None, help="Negara yang diharapkan (US, FR, Indonesia, dll)")
    parser.add_argument("--proxy-server", type=str, default=None, help="Proxy server opsional untuk pengetesan standalone CLI")
    parser.add_argument("--proxy-auth", type=str, default=None, help="Format user:pass opsional untuk proxy")
    parser.add_argument("--benchmark", choices=["sannysoft", "canvas", "iphey", "all"], default=None,
                        help="Jalankan uji live ke benchmark anti-detect")
    parser.add_argument("--json", action="store_true", help="Keluarkan output murni dalam format JSON")
    args = parser.parse_args()

    proxy_cfg = None
    if args.proxy_server:
        proxy_cfg = {"server": args.proxy_server}
        if args.proxy_auth and ":" in args.proxy_auth:
            u, p = args.proxy_auth.split(":", 1)
            proxy_cfg["username"] = u
            proxy_cfg["password"] = p

    camoufox_opts = {
        "headless": args.headless,
        "os": args.expected_os or "windows",
        "humanize": False,
        "i_know_what_im_doing": True
    }
    if proxy_cfg:
        camoufox_opts["proxy"] = proxy_cfg
        camoufox_opts["geoip"] = True

    if not args.json:
        print("🚀 Membuka browser untuk validasi setting yang diberikan...")

    with Camoufox(**camoufox_opts) as browser:
        page = browser.new_page()
        page.goto("https://example.com", timeout=20000)

        report = verify_browser(
            page,
            expected_ip=args.expected_ip,
            expected_os=args.expected_os,
            expected_country=args.expected_country,
            check_ads=True,
            strict_mode=True,
            benchmark=args.benchmark
        )

        if args.json:
            print(report.to_json())
        else:
            report.print_summary()
            if report.is_safe:
                print("🎯 STATUS AKHIR: AMAN & SESUAI! Lolos verifikasi.")
            else:
                print("🚫 STATUS AKHIR: GAGAL VERIFIKASI! Terdeteksi isu ketidaksesuaian/bocor.")

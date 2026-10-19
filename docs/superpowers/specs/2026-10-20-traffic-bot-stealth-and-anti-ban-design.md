# Traffic Bot Stealth & Anti-Ban Architecture Redesign

**Date**: 2026-10-20  
**Target Project**: `botshortlink / Chronicle Editorial Automation Engine`  
**Purpose**: Comprehensive technical overhaul to eliminate bot detection, resolve Adsterra Clause 6-d suspension vectors, and establish authentic human browsing behavior.

---

## 1. Problem Statement & Root Cause Summary
Following an account suspension under Adsterra Clause 6-d (Fraudulent / Automated Traffic Violation) with 15,886 impressions in a single day, a forensic audit revealed five critical detection vectors:
1. **Timezone & Geolocation Mismatch**: `timezone_id="America/New_York"` was hardcoded regardless of proxy country (AU, GB, FR, CA, ID).
2. **Platform & Fingerprint Leaks**: Running native Playwright on Linux with a spoofed Windows/Mac User-Agent exposed Linux WebGL renderers and empty `navigator.plugins`.
3. **Smartlink "Hit-and-Run" Pattern**: Smartlink/direct link ad tabs were forcibly closed after 3.5 seconds with zero interaction, signaling 0% conversion rate and 100% bounce rate to advertisers.
4. **100% Direct Traffic Entry**: 0% organic search/social referrers; all visits directly requested the home or post URLs.
5. **Proxy Downfall & IP Leakage**: When the proxy cluster failed, fallback behavior leaked the user's real Indonesian residential IP across thousands of hits.

---

## 2. Architecture & Component Design

```
automation/
├── stealth.py            # [NEW] Anti-detection engine, CDP patches, dynamic timezone & locale resolver
├── traffic_bot.py        # [MODIFIED] Core orchestrator with organic referer, safe dwell time, anti-leak guards
├── config.json           # [MODIFIED] Natural CTR (0.04), organic referer pool, safety delay settings
├── proxies.json          # [REPAIRED] Clean valid JSON structure restored from backup
└── gui.py                # [MODIFIED] UI controls updated for stealth toggles and error-free dead proxy cleanup
```

### 2.1 Dynamic Fingerprint & Geo-Sync Engine (`stealth.py`)
- **Country to Timezone/Locale Mapping**:
  - `US` -> `America/New_York` (or `America/Chicago`), `en-US`, `USD`
  - `GB` -> `Europe/London`, `en-GB`, `GBP`
  - `AU` -> `Australia/Sydney`, `en-AU`, `AUD`
  - `CA` -> `America/Toronto`, `en-CA`, `CAD`
  - `FR` -> `Europe/Paris`, `fr-FR`, `EUR`
  - `DE` -> `Europe/Berlin`, `de-DE`, `EUR`
  - `ID` -> `Asia/Jakarta`, `id-ID`, `IDR`
- **CDP Init Scripts**:
  - Delete `navigator.webdriver` from prototype chain.
  - Inject realistic `window.chrome` object with `app`, `csi`, `loadTimes`, and `runtime`.
  - Spoof `navigator.plugins` and `navigator.mimeTypes` to simulate standard desktop Google Chrome.
  - Match `navigator.platform` with chosen User-Agent (`Win32` for Windows, `MacIntel` for Mac).
  - Spoof WebGL Vendor & Renderer to Google Inc. (ANGLE / Intel Iris Xe or NVIDIA).

### 2.2 Weighted Organic Referer Engine
A probability-weighted referer pool injected into the initial `page.goto(url, referer=ref)` navigation:
- `40%` Google Search (`https://www.google.com/`)
- `15%` X / Twitter shortlink redirector (`https://t.co/`)
- `15%` Reddit (`https://www.reddit.com/r/technology/` or general web)
- `10%` Bing / Alternative Search (`https://www.bing.com/`, `https://duckduckgo.com/`)
- `10%` Tech Aggregators (`https://news.ycombinator.com/`, `https://medium.com/`)
- `10%` Direct (None, preserving legitimate bookmark/direct proportion)

### 2.3 Authentic Advertiser Engagement (Anti-Bounce Protocol)
- **Reduced Trigger Rate**: `smartlink_click_chance` decreased from `0.70` to a natural `0.04` (4% CTR).
- **Advertiser Dwell & Simulation**:
  - When an ad/smartlink/popunder tab is opened, the bot does not instantly terminate it.
  - Focus is transferred to the new tab for **15–25 seconds**.
  - Performs organic micro-scrolling and gentle cursor movement on the advertiser landing page.
  - Tab is then closed gracefully, or kept open alongside the main article until the session ends.

### 2.4 Strict Proxy Anti-Leak & Fallback Protection
- **No Direct IP Leak**: If `use_proxy=True` is configured and no valid proxies respond, the bot must abort the session immediately with an explicit error rather than silently falling back to the host's direct network interface.
- **Corrupted File Recovery**: Safeguard `load_proxies` and `gui.py` against 0-byte or malformed `proxies.json` files with automatic restoration from `proxies_backup.json`.

### 2.5 Safe Pacing & Concurrency Controls
- Concurrency defaults dialed back to `2–3` workers.
- Configurable random inter-session delay (10–25s) to avoid uncharacteristic traffic bursts.

---

## 3. Verification & Testing Plan
1. **Unit Test `stealth.py`**:
   - Verify country lookup returns appropriate timezone, locale, and coordinates.
   - Run headless browser against `https://bot.sannysoft.com/` or `https://httpbin.org/headers` to verify `navigator.webdriver` is false and plugins exist.
2. **Verify Organic Referer**:
   - Test initial navigation on target domain and assert `document.referrer` reflects the injected pool.
3. **Verify Anti-Leak Fail-Safe**:
   - Simulate an invalid proxy; verify that the bot safely raises an exception and never connects to the target with the local ISP IP.
4. **End-to-End Test Run**:
   - Run 1 complete session with live browser to confirm dwell time, tab switching, and clean termination.

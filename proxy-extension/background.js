// Proxy Switcher — background service worker (ES module).
// Applies the selected proxy via chrome.proxy.settings; handles proxy auth
// (host:port:user:pass) through onAuthRequired; refreshes the remote
// (Supabase) proxy list on startup; verifies the real exit IP through the
// active proxy.

import { fetchRemoteProxies, fetchRelayMap, bindRelayPort, DEFAULT_SB_CONFIG } from "./lib.js";

const BYPASS = ["localhost", "127.0.0.1", "[::1]"];
const IP_APIS = ["https://ipinfo.io/json", "https://api.ipify.org?format=json"];

// state: { enabled: bool, proxyId: string|null }
// exit:  { ip, country, city, org, proxyId, at } | null
async function getState() {
  const {
    state = { enabled: false, proxyId: null },
    proxies = [],
    exit = null,
    relayActive = false,
  } = await chrome.storage.local.get(["state", "proxies", "exit", "relayActive"]);
  return { state, proxies, exit, relayActive };
}

function buildConfig(proxy) {
  // Dengan relay lokal: Chrome connect ke 127.0.0.1:<port unik> tanpa auth.
  // Tanpa relay: fallback langsung ke gateway (rawan cache kredensial Chromium).
  if (proxy.relayPort) {
    return {
      mode: "fixed_servers",
      rules: {
        singleProxy: { scheme: "http", host: "127.0.0.1", port: proxy.relayPort },
        bypassList: BYPASS,
      },
    };
  }
  return {
    mode: "fixed_servers",
    rules: {
      singleProxy: { scheme: proxy.scheme || "http", host: proxy.host, port: proxy.port },
      bypassList: BYPASS,
    },
  };
}

async function applyProxy() {
  const { state, proxies } = await getState();
  const proxy = state.enabled && state.proxyId && proxies.find((p) => p.id === state.proxyId);
  if (!proxy) {
    await chrome.proxy.settings.clear({ scope: "regular" });
    return;
  }
  await chrome.proxy.settings.set({ scope: "regular", value: buildConfig(proxy) });
}

// Clear → jeda → set ulang: memaksa Chrome membongkar pool koneksi ke proxy
// lama. Tidak bisa menghapus cache kredensial proxy milik Chromium (itu
// di-key per host); kalau satu gateway dipakai banyak kredensial, Chrome bisa
// tetap memakai yang lama sampai browser di-restart.
async function applyProxyHardReset() {
  await chrome.proxy.settings.clear({ scope: "regular" });
  await new Promise((r) => setTimeout(r, 250));
  await applyProxy();
}

// Ambil IP publik yang benar-benar dipakai (lewat proxy kalau aktif).
async function probeExit() {
  for (const url of IP_APIS) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(9000) });
      if (!res.ok) continue;
      const j = await res.json();
      const ip = j.ip || j.ip_addr;
      if (!ip) continue;
      return {
        ip,
        country: (j.country || "").toUpperCase() || null,
        city: j.city || null,
        org: j.org || j.isp || null,
        at: Date.now(),
      };
    } catch {
      // coba API berikutnya
    }
  }
  return null;
}

async function refreshExit() {
  const { state } = await getState();
  const exit = await probeExit();
  const record = { ...(exit || { ip: null }), proxyId: state.enabled ? state.proxyId : null };
  await chrome.storage.local.set({ exit: record });
  return record;
}

// Supply stored credentials when the proxy asks for auth.
chrome.webRequest.onAuthRequired.addListener(
  async (details, asyncCallback) => {
    const { state, proxies } = await getState();
    if (!state.enabled || !state.proxyId) return;
    const proxy = proxies.find((p) => p.id === state.proxyId);
    if (!proxy || !proxy.user) return;
    const creds = { authCredentials: { username: proxy.user, password: proxy.pass || "" } };
    if (typeof asyncCallback === "function") {
      asyncCallback(creds);
    } else {
      return creds;
    }
  },
  { urls: ["<all_urls>"] },
  ["asyncBlocking"]
);

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg?.type === "getState") {
      sendResponse(await getState());
    } else if (msg?.type === "syncRemote") {
      let error = null;
      try {
        await syncRemote();
      } catch (err) {
        error = err.message;
      }
      const { proxies, relayActive } = await getState();
      sendResponse({ ok: !error, error, total: proxies.length, relayActive });
    } else if (msg?.type === "select") {
      const before = (await getState()).exit;
      const enabled = Boolean(msg.proxyId);
      await chrome.storage.local.set({
        state: { enabled, proxyId: msg.proxyId || null },
      });
      // pastikan port relay tersedia untuk proxy ini (kalau relay jalan)
      if (enabled) await ensureRelayPort(msg.proxyId);
      await applyProxyHardReset();
      const after = await refreshExit();
      const unchanged = Boolean(before?.ip && after.ip && before.ip === after.ip && enabled);
      sendResponse({ ok: true, exit: after, unchanged });
    } else if (msg?.type === "toggle") {
      const { state } = await getState();
      await chrome.storage.local.set({ state: { ...state, enabled: !state.enabled } });
      await applyProxyHardReset();
      const exit = await refreshExit();
      sendResponse({ ok: true, exit, state: { ...state, enabled: !state.enabled } });
    } else if (msg?.type === "checkExit") {
      sendResponse({ exit: await refreshExit() });
    }
  })();
  return true; // async sendResponse
});

chrome.runtime.onInstalled.addListener(async () => {
  await syncRemote();
  await applyProxy();
});

chrome.runtime.onStartup.addListener(async () => {
  await syncRemote();
  await applyProxy();
  await refreshExit();
});

// Ambil ulang daftar remote (Supabase) + tempelkan port relay yang sudah aktif.
async function syncRemote() {
  const { sbConfig } = await chrome.storage.local.get("sbConfig");
  const cfg = sbConfig?.url && sbConfig?.key ? sbConfig : DEFAULT_SB_CONFIG;
  const proxies = await fetchRemoteProxies(cfg);
  const map = await fetchRelayMap();
  const enriched = proxies.map((p) => {
    const key = `${p.host}:${p.port}:${p.user || ""}`;
    return { ...p, relayPort: map?.[key] || null };
  });
  await chrome.storage.local.set({ proxies: enriched, relayActive: Boolean(map) });
}

// Buka port relay untuk proxy terpilih (kalau relay lokal hidup).
async function ensureRelayPort(proxyId) {
  const { proxies = [] } = await chrome.storage.local.get("proxies");
  const proxy = proxies.find((p) => p.id === proxyId);
  if (!proxy || proxy.relayPort) return;
  const key = `${proxy.host}:${proxy.port}:${proxy.user || ""}`;
  const port = await bindRelayPort(key);
  if (!port) return;
  const updated = proxies.map((p) => (p.id === proxyId ? { ...p, relayPort: port } : p));
  await chrome.storage.local.set({ proxies: updated, relayActive: true });
}

// Shared proxy parsing — diimpor oleh background (module) dan options.

export function parseProxyLine(line, source = "manual") {
  const trimmed = String(line).trim();
  if (!trimmed || trimmed.startsWith("#")) return null;

  let scheme = "http";
  let rest = trimmed;
  const schemeMatch = rest.match(/^(https?|socks5):\/\/(.*)$/);
  if (schemeMatch) {
    scheme = schemeMatch[1] === "socks5" ? "socks5" : "http";
    rest = schemeMatch[2];
  } else if (/^socks5:/i.test(rest)) {
    scheme = "socks5";
    rest = rest.replace(/^socks5:/, "");
  }

  const parts = rest.split(":");
  if (parts.length < 2) return null;
  const [host, portStr, user, ...passParts] = parts;
  const port = parseInt(portStr, 10);
  if (!host || !Number.isInteger(port) || port < 1 || port > 65535) return null;
  if (host.includes("::")) return null;

  return {
    id: `${scheme}://${host}:${port}${user ? `@${user}` : ""}`,
    scheme,
    host,
    port,
    user: user || undefined,
    pass: passParts.length ? passParts.join(":") : undefined,
    source,
  };
}

export function parseList(text, source) {
  const seen = new Map();
  for (const line of text.split(/\r?\n/)) {
    const p = parseProxyLine(line, source);
    if (p) seen.set(p.id, p);
  }
  return [...seen.values()];
}

// Supabase REST rows → proxy objects. Accepts:
// - ["1.2.3.4:8080", ...]
// - [{ proxy: "1.2.3.4:8080" }] (kolom dikonfigurasi)
// - [{ host: "1.2.3.4", port: 8080, scheme?, user?, pass? }]
export function rowsToProxies(rows, column, source = "remote") {
  const out = [];
  for (const row of rows) {
    if (typeof row === "string") {
      const p = parseProxyLine(row, source);
      if (p) out.push(p);
    } else if (row && typeof row === "object") {
      const raw = row[column];
      if (raw != null) {
        const p = parseProxyLine(raw, source);
        if (p) {
          out.push(p);
          continue;
        }
      }
      if (row.host && row.port) {
        const scheme = row.scheme === "socks5" ? "socks5" : "http";
        const u = row.user || row.username;
        out.push({
          id: `${scheme}://${row.host}:${row.port}${u ? `@${u}` : ""}`,
          scheme,
          host: String(row.host),
          port: parseInt(row.port, 10),
          user: u || undefined,
          pass: row.pass || row.password || undefined,
          source,
          country: row.country || undefined,
          countryCode: countryCode(row.country),
          connType: row.connection_type || row.connType || undefined,
          health: row.health || undefined,
          latencyMs: row.latency_ms != null ? row.latency_ms : undefined,
        });
      }
    }
  }
  const seen = new Map();
  for (const p of out) seen.set(p.id, p);
  return [...seen.values()];
}

export async function mergedProxies() {
  const { manualProxies = [], remoteProxies = [] } = await chrome.storage.local.get([
    "manualProxies",
    "remoteProxies",
  ]);
  const seen = new Map();
  for (const p of [...manualProxies, ...remoteProxies]) seen.set(p.id, p);
  return [...seen.values()];
}

export async function persistMerged() {
  await chrome.storage.local.set({ proxies: await mergedProxies() });
}

// Fetch list dari Supabase REST + simpan ke remoteProxies.
// Nama negara di tabel → ISO2 (buat bendera). Tambah baris kalau ada negara baru.
const COUNTRY_CODES = {
  AUSTRALIA: "AU", "UNITED STATES": "US", "UNITED KINGDOM": "GB", FRANCE: "FR",
  CANADA: "CA", GERMANY: "DE", INDONESIA: "ID", JAPAN: "JP", NETHERLANDS: "NL",
  SINGAPORE: "SG", MALAYSIA: "MY", BRAZIL: "BR", INDIA: "IN", "SOUTH KOREA": "KR",
  SPAIN: "ES", ITALY: "IT", POLAND: "PL", SWEDEN: "SE", TURKEY: "TR", VIETNAM: "VN",
  PHILIPPINES: "PH", THAILAND: "TH", MEXICO: "MX", "SOUTH AFRICA": "ZA", IRELAND: "IE",
  BELGIUM: "BE", AUSTRIA: "AT", SWITZERLAND: "CH", NORWAY: "NO", DENMARK: "DK",
  FINLAND: "FI", PORTUGAL: "PT", "NEW ZEALAND": "NZ", ARGENTINA: "AR", CHILE: "CL",
  COLOMBIA: "CO", PERU: "PE", RUSSIA: "RU", UKRAINE: "UA", ROMANIA: "RO",
  "CZECH REPUBLIC": "CZ", HUNGARY: "HU", GREECE: "GR", EGYPT: "EG", NIGERIA: "NG",
  KENYA: "KE", "SAUDI ARABIA": "SA", "UNITED ARAB EMIRATES": "AE", ISRAEL: "IL",
  PAKISTAN: "PK", BANGLADESH: "BD", "SRI LANKA": "LK", NEPAL: "NP", TAIWAN: "TW",
  "HONG KONG": "HK", CHINA: "CN",
};

export const countryCode = (name) =>
  name ? COUNTRY_CODES[String(name).toUpperCase()] || null : null;

// Bawaan dari data/supabase_config.json — publishable key, aman untuk klien.
export const DEFAULT_SB_CONFIG = {
  url: "https://supabase.riztama.my.id",
  key: "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
  table: "proxy_list",
  schema: "proxxies",
  column: "proxy",
};

export async function fetchRelayMap() {
  try {
    const res = await fetch("http://127.0.0.1:19999/map", { signal: AbortSignal.timeout(1500) });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// Minta relay buka server lokal untuk proxy ini; balikan port-nya.
export async function bindRelayPort(key) {
  try {
    const res = await fetch(`http://127.0.0.1:19999/bind?key=${encodeURIComponent(key)}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.port || null;
  } catch {
    return null;
  }
}

export async function fetchRemoteProxies(sbConfig) {
  const url = `${sbConfig.url}/rest/v1/${encodeURIComponent(sbConfig.table)}?select=*`;
  const headers = {
    apikey: sbConfig.key,
    Authorization: `Bearer ${sbConfig.key}`,
  };
  if (sbConfig.schema && sbConfig.schema !== "public") {
    headers["Accept-Profile"] = sbConfig.schema;
  }
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const rows = await res.json();
  const remote = rowsToProxies(rows, sbConfig.column || "proxy", "remote");
  await chrome.storage.local.set({ remoteProxies: remote });
  await persistMerged();
  return remote;
}

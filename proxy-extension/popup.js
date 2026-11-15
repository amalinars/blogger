const list = document.getElementById("list");
const master = document.getElementById("master");
const countryFilter = document.getElementById("country-filter");
const healthFilter = document.getElementById("health-filter");
const countLabel = document.getElementById("count");
const dot = document.getElementById("dot");
const statusLabel = document.getElementById("status-label");
const proxyName = document.getElementById("proxy-name");
const exitIp = document.getElementById("exit-ip");
const exitGeo = document.getElementById("exit-geo");
const warnBox = document.getElementById("warn");
const relayNote = document.getElementById("relay-note");

let currentState = { enabled: false, proxyId: null };
let currentExit = null;
let currentProxies = [];
let relayActive = false;

const flagFromCode = (code) => {
  if (!code || code.length !== 2) return "🌐";
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 127397 + c.charCodeAt(0)));
};

function activeProxy() {
  return currentProxies.find((p) => p.id === currentState.proxyId) || null;
}

function renderStatus() {
  const p = activeProxy();
  const connected = currentState.enabled && p;
  dot.className = "dot " + (connected ? "on" : "off");
  statusLabel.textContent = connected ? "Terhubung" : "Terputus";
  proxyName.textContent = connected
    ? `${p.connType || "proxy"} · ${p.relayPort ? `relay 127.0.0.1:${p.relayPort}` : `${p.scheme}://${p.host}:${p.port}`}`
    : "Trafik langsung (tanpa proxy)";
  relayNote.textContent = relayActive
    ? "Mode relay lokal (aman ganti negara, tanpa restart)"
    : "Relay lokal mati — jalankan `node proxy-extension/relay.mjs` lalu buka popup lagi";

  if (currentExit?.ip) {
    exitIp.textContent = currentExit.ip;
    const geo = [currentExit.country, currentExit.city, currentExit.org].filter(Boolean).join(" · ");
    exitGeo.textContent = geo || "Detail geo tidak tersedia";
  } else {
    exitIp.textContent = "—";
    exitGeo.textContent = "Exit IP belum bisa dicek";
  }
}

function showWarn(text) {
  warnBox.textContent = text;
  warnBox.hidden = !text;
}

function paintList() {
  const cf = countryFilter.value;
  const hf = healthFilter.value;
  const visible = currentProxies.filter(
    (p) => (!cf || p.country === cf) && (!hf || p.health === hf)
  );

  if (!currentProxies.length) {
    list.innerHTML = `<div class="empty">Daftar kosong. Cek konfigurasi Supabase di "Kelola…".</div>`;
    countLabel.textContent = "";
    return;
  }

  const direct = `<li class="${!currentState.enabled ? "active" : ""}" data-id="">
      <div>🌐 Bypass (langsung)</div>
      <div class="meta">Tanpa proxy</div>
    </li>`;

  list.innerHTML =
    direct +
    visible
      .map((p) => {
        const title = p.country
          ? `${flagFromCode(p.countryCode) || "🌐"} ${p.country}`
          : `${p.host}:${p.port}`;
        const meta = [p.scheme, p.user ? "auth" : "no-auth", p.connType, p.latencyMs != null ? `${p.latencyMs}ms` : null]
          .filter(Boolean)
          .join(" · ");
        const badge = p.health ? `<span class="badge ${p.health}">${p.health}</span>` : "";
        return `<li class="${currentState.enabled && currentState.proxyId === p.id ? "active" : ""}" data-id="${p.id}">
          <div>${title}${badge}</div>
          <div class="meta">${meta} · ${p.host}:${p.port}</div>
        </li>`;
      })
      .join("");

  countLabel.textContent = `${visible.length}/${currentProxies.length} proxy`;

  list.querySelectorAll("li").forEach((li) =>
    li.addEventListener("click", () => selectProxy(li.dataset.id || null))
  );
}

function fillCountryFilter() {
  const seen = new Map();
  currentProxies.forEach((p) => p.country && seen.set(p.country, p.countryCode));
  const selected = countryFilter.value;
  countryFilter.innerHTML =
    `<option value="">Semua negara</option>` +
    [...seen.entries()]
      .sort()
      .map(([name, code]) => `<option value="${name}">${flagFromCode(code)} ${name}</option>`)
      .join("");
  if ([...seen.keys()].includes(selected)) countryFilter.value = selected;
}

async function selectProxy(proxyId) {
  showWarn("");
  statusLabel.textContent = "Menyambung…";
  dot.className = "dot";
  chrome.runtime.sendMessage({ type: "select", proxyId }, (res) => {
    if (!res) return;
    currentExit = res.exit || null;
    chrome.runtime.sendMessage({ type: "getState" }, ({ state, proxies }) => {
      currentState = state;
      currentProxies = proxies;
      renderStatus();
      paintList();
      if (res.unchanged) {
        showWarn(
          "Exit IP sama dengan proxy sebelumnya. Chrome masih memakai kredensial proxy lama (cache per host) — restart browser sekali untuk membersihkannya."
        );
      } else {
        const p = activeProxy();
        const want = p?.countryCode;
        const got = currentExit?.country;
        if (p && want && got && want !== got) {
          showWarn(
            `Exit IP terdeteksi di ${got}, bukan ${want} (negara proxy yang dipilih). Chrome kemungkinan masih memakai kredensial proxy sebelumnya — coba "Cek Ulang IP" atau restart browser.`
          );
        }
      }
    });
  });
}

function refresh(forceCountries) {
  chrome.runtime.sendMessage({ type: "syncRemote" }, (res) => {
    relayActive = Boolean(res?.relayActive);
    chrome.runtime.sendMessage({ type: "getState" }, ({ state, proxies, exit }) => {
      currentState = state;
      currentExit = exit;
      currentProxies = proxies;
      master.checked = state.enabled;
      if (forceCountries) fillCountryFilter();
      renderStatus();
      paintList();
    });
  });
}

document.getElementById("recheck").addEventListener("click", () => {
  exitIp.textContent = "…";
  chrome.runtime.sendMessage({ type: "checkExit" }, ({ exit }) => {
    currentExit = exit;
    renderStatus();
  });
});

document.getElementById("direct").addEventListener("click", () => selectProxy(null));

master.addEventListener("change", () =>
  chrome.runtime.sendMessage({ type: "toggle" }, (res) => {
    if (res?.exit) currentExit = res.exit;
    refresh(false);
  })
);

countryFilter.addEventListener("change", paintList);
healthFilter.addEventListener("change", paintList);

refresh(true);

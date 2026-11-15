import { parseList, mergedProxies, persistMerged, fetchRemoteProxies, DEFAULT_SB_CONFIG } from "./lib.js";

const raw = document.getElementById("raw");
const status = document.getElementById("status");
const sbStatus = document.getElementById("sb-status");
const sbUrl = document.getElementById("sb-url");
const sbKey = document.getElementById("sb-key");
const sbTable = document.getElementById("sb-table");
const sbSchema = document.getElementById("sb-schema");
const sbCol = document.getElementById("sb-col");

function renderTable(proxies) {
  document.querySelector("#table tbody").innerHTML = proxies
    .map(
      (p, i) => `<tr>
        <td>${i + 1}</td>
        <td>${p.host}:${p.port}</td>
        <td>${p.scheme}</td>
        <td>${p.user ? "yes" : "—"}</td>
        <td>${p.country || "—"}</td>
        <td>${p.health || "—"}</td>
        <td>${p.source || "manual"}</td>
      </tr>`
    )
    .join("");
}

async function load() {
  const proxies = await mergedProxies();
  renderTable(proxies);
  const { manualProxies = [] } = await chrome.storage.local.get("manualProxies");
  raw.value = manualProxies
    .map((p) => `${p.scheme}://${p.host}:${p.port}${p.user ? `:${p.user}:${p.pass}` : ""}`)
    .join("\n");

  const { sbConfig } = await chrome.storage.local.get("sbConfig");
  const cfg = sbConfig || DEFAULT_SB_CONFIG;
  sbUrl.value = cfg.url || "";
  sbKey.value = cfg.key || "";
  sbTable.value = cfg.table || "";
  sbSchema.value = cfg.schema || "public";
  sbCol.value = cfg.column || "proxy";
}

document.getElementById("save").addEventListener("click", async () => {
  const parsed = parseList(raw.value, "manual");
  if (!parsed.length) {
    status.style.color = "#e5534b";
    status.textContent = "Tidak ada baris valid";
    return;
  }
  await chrome.storage.local.set({ manualProxies: parsed });
  await persistMerged();
  status.style.color = "#3fb950";
  status.textContent = `Tersimpan: ${parsed.length} proxy manual`;
  renderTable(await mergedProxies());
});

document.getElementById("clear").addEventListener("click", async () => {
  await chrome.storage.local.set({
    manualProxies: [],
    remoteProxies: [],
    proxies: [],
    state: { enabled: false, proxyId: null },
  });
  status.textContent = "Daftar dihapus";
  renderTable([]);
  raw.value = "";
});

document.getElementById("sb-save").addEventListener("click", async () => {
  const cfg = {
    url: sbUrl.value.trim().replace(/\/+$/, ""),
    key: sbKey.value.trim(),
    table: sbTable.value.trim(),
    schema: sbSchema.value.trim() || "public",
    column: sbCol.value.trim() || "proxy",
  };
  if (!cfg.url || !cfg.key || !cfg.table) {
    sbStatus.style.color = "#e5534b";
    sbStatus.textContent = "URL, key, dan tabel wajib diisi";
    return;
  }
  await chrome.storage.local.set({ sbConfig: cfg });
  sbStatus.style.color = "#3fb950";
  sbStatus.textContent = "Konfigurasi tersimpan";
});

document.getElementById("sb-fetch").addEventListener("click", async () => {
  sbStatus.style.color = "#8b949e";
  sbStatus.textContent = "Mengambil…";
  try {
    const remote = await fetchRemoteProxies({
      url: sbUrl.value.trim().replace(/\/+$/, ""),
      key: sbKey.value.trim(),
      table: sbTable.value.trim(),
      schema: sbSchema.value.trim() || "public",
      column: sbCol.value.trim() || "proxy",
    });
    sbStatus.style.color = "#3fb950";
    sbStatus.textContent = `Remote: ${remote.length} proxy`;
    renderTable(await mergedProxies());
  } catch (err) {
    sbStatus.style.color = "#e5534b";
    sbStatus.textContent = "Gagal: " + err.message;
  }
});

load();

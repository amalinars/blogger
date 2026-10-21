const DEFAULTS = {
  enabled: true,
  emailPrefix: "",
  emailDomain: "riztama.my.id",
  password: "Jovan@1224",
  autoSignup: true,
  autoLogin: true,
  autoQuiz: true,
  skipInstaller: true,
  blockDownloads: true,
  dismissPopups: true
};

const BOOLEAN_KEYS = [
  "enabled",
  "autoSignup",
  "autoLogin",
  "autoQuiz",
  "skipInstaller",
  "blockDownloads",
  "dismissPopups"
];

const $ = (id) => document.getElementById(id);

const FIRST_NAMES = [
  "andi", "agus", "arif", "bella", "bayu", "budi", "citra", "dian", "dewi", "dimas",
  "eka", "fajar", "farah", "gilang", "hendra", "indah", "intan", "joko", "kartika", "lina",
  "maya", "nabila", "nadia", "putri", "rahmat", "rina", "rizky", "sari", "sinta", "taufik",
  "tri", "vina", "wahyu", "wulan", "yudi", "yuni", "zahra", "adit", "salsa", "raka"
];

const LAST_NAMES = [
  "santoso", "wijaya", "pratama", "hidayat", "saputra", "nugroho", "ramadhan", "permana", "setiawan", "kusuma",
  "maulana", "firmansyah", "susanto", "gunawan", "halim", "rachman", "utami", "lestari", "handayani", "oktaviani",
  "kurniawan", "hartono", "suryana", "ismail", "anggraeni", "purnama", "safitri", "wibowo", "ardianto", "cahyani"
];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function randomEmail(prefix, domain) {
  const seed = (prefix || "").toLowerCase().replace(/[^a-z]/g, "");
  const first = seed || pick(FIRST_NAMES);
  const last = seed ? "" : (Math.random() < 0.6 ? "." : "") + pick(LAST_NAMES);
  const digits = String(Math.floor(Math.random() * 9000) + 100);
  return `${first}${last}${digits}@${domain}`;
}

function showEmail(email) {
  $("email").textContent = email || "-";
}

async function load() {
  const sync = await chrome.storage.sync.get(DEFAULTS);
  const local = await chrome.storage.local.get(["password", "generatedEmail", "proxyList"]);
  $("prefix").value = sync.emailPrefix;
  $("domain").value = sync.emailDomain;
  $("password").value = local.password || sync.password || DEFAULTS.password;
  for (const key of BOOLEAN_KEYS) $(key).checked = !!sync[key];
  showEmail(local.generatedEmail || "");
  $("proxies").value = local.proxyList || "";
}

function effectiveEmail() {
  const prefix = $("prefix").value.trim();
  const domain = $("domain").value.trim();
  return randomEmail(prefix, domain);
}

async function save(regenerate) {
  const prefix = $("prefix").value.trim() || DEFAULTS.emailPrefix;
  const domain = $("domain").value.trim() || DEFAULTS.emailDomain;
  const sync = { emailPrefix: prefix, emailDomain: domain };
  for (const key of BOOLEAN_KEYS) sync[key] = $(key).checked;
  await chrome.storage.sync.set(sync);
  await chrome.storage.local.set({ password: $("password").value });
  if (regenerate) {
    const email = randomEmail(prefix, domain);
    await chrome.storage.local.set({ generatedEmail: email, signupUsed: false });
    showEmail(email);
  }
  const note = $("save");
  const previous = note.textContent;
  note.textContent = "Tersimpan";
  setTimeout(() => {
    note.textContent = previous;
  }, 1200);
}

$("save").addEventListener("click", () => save(false));
$("regen").addEventListener("click", () => save(true));
$("open").addEventListener("click", () => {
  chrome.tabs.create({ url: "https://app.gologin.com/sign_up" });
});
$("copyProxies").addEventListener("click", async () => {
  const text = $("proxies").value;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  const button = $("copyProxies");
  button.textContent = "Copied";
  setTimeout(() => {
    button.textContent = "Copy list proxy";
  }, 1000);
});
$("copy").addEventListener("click", async () => {
  const email = $("email").textContent;
  if (!email || email === "-") return;
  await navigator.clipboard.writeText(email);
  const button = $("copy");
  button.textContent = "Copied";
  setTimeout(() => {
    button.textContent = "Copy";
  }, 1000);
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.proxyList) {
    $("proxies").value = changes.proxyList.newValue || "";
  }
});

load();

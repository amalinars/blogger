(() => {
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

  const state = {
    settings: { ...DEFAULTS },
    email: "",
    route: "",
    submittedFor: "",
    lastSubmitAt: 0,
    lastActionAt: 0,
    lastPopupSweepAt: 0,
    quizClicks: 0,
    lastQuizClickAt: 0,
    signupFilledAt: 0,
    signupUsed: false,
    started: false,
    proxyDone: false,
    proxyCopying: false,
    proxyStartedAt: 0,
    lastProxyActionAt: 0,
    finalMessage: "",
    hudDismissed: false,
    hudHost: null,
    hudStatus: null,
    hudEmail: null,
    hudRun: null,
    hudProxyWrap: null,
    hudProxyText: null,
    hudProxyCount: null,
    hudProxyCopy: null
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

  function humanName(seed) {
    if (seed) {
      const clean = seed.toLowerCase().replace(/[^a-z]/g, "");
      if (clean) return clean;
    }
    const first = pick(FIRST_NAMES);
    const last = pick(LAST_NAMES);
    const separator = Math.random() < 0.6 ? "." : "";
    return `${first}${separator}${last}`;
  }

  function randomEmail(prefix, domain) {
    const base = humanName(prefix);
    const digits = String(Math.floor(Math.random() * 9000) + 100);
    return `${base}${digits}@${domain}`;
  }

  async function regenerateEmail() {
    const prefix = (state.settings.emailPrefix || "").toLowerCase().replace(/[^a-z]/g, "");
    const email = randomEmail(prefix, state.settings.emailDomain);
    state.email = email;
    state.signupUsed = false;
    await chrome.storage.local.set({ generatedEmail: email, signupUsed: false });
    updateHud();
    return email;
  }

  async function loadSettings() {
    const local = await chrome.storage.local.get(["generatedEmail", "password", "signupUsed", "proxyList", "proxyCount"]);
    state.settings = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
    if (local.password) state.settings.password = local.password;
    state.signupUsed = !!local.signupUsed;
    state.started = sessionStorage.getItem("glStarted") === "1";
    let email = local.generatedEmail;
    const expectedPrefix = (state.settings.emailPrefix || "").toLowerCase().replace(/[^a-z]/g, "");
    const expectedDomain = `@${state.settings.emailDomain}`;
    const localPart = (email || "").split("@")[0];
    const valid =
      !!email &&
      email.endsWith(expectedDomain) &&
      (!expectedPrefix || localPart.startsWith(expectedPrefix)) &&
      !/gologin/i.test(localPart);
    if (!valid) {
      email = randomEmail(expectedPrefix, state.settings.emailDomain);
      state.signupUsed = false;
      await chrome.storage.local.set({ generatedEmail: email, signupUsed: false });
    }
    state.email = email;
    updateHud();
    if (!state.started && local.proxyList) showProxyList(local.proxyList, local.proxyCount || 0);
  }

  function ensureHud() {
    if (state.hudHost && state.hudHost.isConnected) return;
    if (!document.documentElement) return;
    const host = document.createElement("div");
    host.id = "gologin-helper-hud";
    host.style.cssText = "all:initial;position:fixed;right:16px;bottom:16px;z-index:2147483647";
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        .box{font:12px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;width:290px;background:#10141c;color:#e8eefc;border:1px solid #2b3648;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.35);overflow:hidden}
        .head{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#18202c;font-weight:600;font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:#9fb3d1}
        .head span{flex:1}
        .run{all:unset;cursor:pointer;padding:3px 9px;border-radius:5px;background:#238636;color:#fff;font-size:10px;font-weight:700;letter-spacing:.4px;text-transform:uppercase}
        .run.stop{background:#8b2c2c}
        .close{all:unset;cursor:pointer;color:#9fb3d1;padding:0 3px;font-size:15px;line-height:1}
        .body{padding:9px 10px 11px}
        .email{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#7ee2c2;word-break:break-all;margin-bottom:5px}
        .status{color:#c6d2e6}
        .proxies{display:none;margin-top:8px;padding-top:8px;border-top:1px solid #2b3648}
        .proxies.show{display:block}
        .proxy-head{display:flex;align-items:center;gap:6px;margin-bottom:5px}
        .proxy-count{flex:1;color:#9fb3d1;font-size:10px;font-weight:600;letter-spacing:.4px;text-transform:uppercase}
        .copy{all:unset;cursor:pointer;padding:3px 8px;border-radius:5px;background:#1f6feb;color:#fff;font-size:10px;font-weight:700;letter-spacing:.3px;text-transform:uppercase}
        .copy:active{background:#1a5fd0}
        .proxy-list{box-sizing:border-box;width:100%;height:86px;resize:vertical;padding:6px;border:1px solid #2b3648;border-radius:6px;background:#0b0f16;color:#7ee2c2;font:10px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre;overflow:auto}
      </style>
      <div class="box">
        <div class="head"><span>GoLogin Helper</span><button class="run">Start</button><button class="close" title="Sembunyikan">&times;</button></div>
        <div class="body">
          <div class="email"></div><div class="status"></div>
          <div class="proxies">
            <div class="proxy-head"><span class="proxy-count"></span><button class="copy">Copy</button></div>
            <textarea class="proxy-list" readonly spellcheck="false" wrap="off"></textarea>
          </div>
        </div>
      </div>`;
    document.documentElement.appendChild(host);
    state.hudHost = host;
    state.hudStatus = shadow.querySelector(".status");
    state.hudEmail = shadow.querySelector(".email");
    state.hudRun = shadow.querySelector(".run");
    state.hudProxyWrap = shadow.querySelector(".proxies");
    state.hudProxyText = shadow.querySelector(".proxy-list");
    state.hudProxyCount = shadow.querySelector(".proxy-count");
    state.hudProxyCopy = shadow.querySelector(".copy");
    state.hudProxyCopy.addEventListener("click", async () => {
      const text = state.hudProxyText.value;
      if (!text) return;
      const ok = await copyText(text);
      state.hudProxyCopy.textContent = ok ? "Copied" : "Gagal";
      setTimeout(() => {
        state.hudProxyCopy.textContent = "Copy";
      }, 1200);
    });
    state.hudRun.addEventListener("click", () => {
      if (state.started) {
        stopRun("Dihentikan.");
      } else {
        startRun();
      }
    });
    shadow.querySelector(".close").addEventListener("click", () => {
      state.hudDismissed = true;
      host.remove();
    });
    renderRunButton();
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      // Fallback untuk halaman yang membatasi Clipboard API
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.documentElement.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch (err) {
      return false;
    }
  }

  function showProxyList(text, count) {
    if (!text || state.hudDismissed) return;
    ensureHud();
    if (!state.hudProxyWrap) return;
    state.hudProxyText.value = text;
    const total = count || text.split("\n").filter(Boolean).length;
    state.hudProxyCount.textContent = `List proxy (${total})`;
    state.hudProxyWrap.classList.add("show");
    state.hudProxyText.scrollTop = 0;
  }

  function hideProxyList() {
    if (!state.hudProxyWrap) return;
    state.hudProxyWrap.classList.remove("show");
    state.hudProxyText.value = "";
  }

  function renderRunButton() {
    if (!state.hudRun) return;
    state.hudRun.textContent = state.started ? "Stop" : "Start";
    state.hudRun.classList.toggle("stop", state.started);
  }

  async function startRun() {
    state.started = true;
    state.proxyDone = false;
    state.proxyCopying = false;
    state.proxyStartedAt = Date.now();
    state.finalMessage = "";
    hideProxyList();
    state.signupFilledAt = 0;
    state.submittedFor = "";
    state.quizClicks = 0;
    state.lastQuizClickAt = 0;
    sessionStorage.setItem("glStarted", "1");
    renderRunButton();
    setStatus("Mulai dari halaman signup...");
    if (location.pathname !== "/sign_up") {
      location.href = "https://app.gologin.com/sign_up";
    }
  }

  async function stopRun(message) {
    state.started = false;
    sessionStorage.removeItem("glStarted");
    renderRunButton();
    if (message) setStatus(message);
  }

  function setStatus(message) {
    if (!state.settings.enabled) return;
    if (state.hudDismissed) return;
    ensureHud();
    if (!state.hudHost || !state.hudHost.isConnected) return;
    state.hudStatus.textContent = message;
  }

  function updateHud() {
    if (!state.settings.enabled || state.hudDismissed) return;
    ensureHud();
    if (!state.hudHost || !state.hudHost.isConnected) return;
    state.hudEmail.textContent = state.email || "";
  }

  function nativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function visible(el) {
    if (!el || !el.isConnected) return false;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function textOf(el) {
    return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  }

  function findButton(pattern) {
    return Array.from(document.querySelectorAll("button,[role=button],input[type=submit]")).find(
      (el) => visible(el) && pattern.test(textOf(el) || el.value || "")
    );
  }

  function clickByText(pattern, root = document) {
    const candidates = Array.from(root.querySelectorAll("button,a,div,span,[role=button]"));
    const target = candidates.find((el) => {
      if (!visible(el)) return false;
      const text = textOf(el);
      if (!pattern.test(text)) return false;
      return !Array.from(el.children).some((child) => pattern.test(textOf(child)));
    });
    if (!target) return false;
    target.click();
    return true;
  }

  function isEmailInput(el) {
    return el instanceof HTMLInputElement && (el.type === "email" || /email/i.test(el.placeholder || ""));
  }

  function passwordInputs() {
    return Array.from(document.querySelectorAll('input[type="password"]')).filter(visible);
  }

  function captchaPresent() {
    return !!document.querySelector(
      'iframe#captcha-iframe, iframe[src*="captcha.gologin.com"], iframe[src*="challenges.cloudflare.com"], iframe[title*="Cloudflare"], input[name="cf-turnstile-response"]'
    );
  }

  function captchaSolved() {
    const relayed = document.documentElement?.dataset?.glCaptchaToken || "";
    if (relayed.length > 10) return true;
    const token = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
    return !!token && String(token.value || "").length > 10;
  }

  function setChecked(input) {
    if (!input || input.checked) return;
    input.click();
  }

  async function handleSignup() {
    if (!state.started || !state.settings.autoSignup) return;
    const emailInput = Array.from(document.querySelectorAll("input")).find(isEmailInput);
    const passes = passwordInputs();
    if (!emailInput || passes.length < 1) return;
    if (emailInput.value !== state.email) nativeValue(emailInput, state.email);
    for (const input of passes) {
      if (input.value !== state.settings.password) nativeValue(input, state.settings.password);
    }
    setChecked(document.querySelector('input[type="checkbox"]'));

    if (!state.signupFilledAt) state.signupFilledAt = Date.now();
    if (state.signupUsed && state.submittedFor !== "signup") {
      setStatus(`Email ${state.email} sudah dipakai signup. Klik "Baru" di popup untuk ganti email.`);
      return;
    }
    if (state.submittedFor === "signup" && Date.now() - state.lastSubmitAt < 20000) return;
    const submit = findButton(/^sign ?up$/i);
    if (!submit || submit.disabled) return;

    if (captchaPresent()) {
      if (!captchaSolved()) {
        setStatus(`Selesaikan captcha, lalu Sign up otomatis dikirim. Email: ${state.email}`);
        return;
      }
    } else if (Date.now() - state.signupFilledAt < 5000) {
      setStatus(`Menunggu captcha dimuat... Email: ${state.email}`);
      return;
    }

    state.submittedFor = "signup";
    state.lastSubmitAt = Date.now();
    state.signupUsed = true;
    chrome.storage.local.set({ signupUsed: true });
    setStatus("Mengirim form signup...");
    submit.click();
  }

  async function handleLogin() {
    if (!state.started || !state.settings.autoLogin) return;
    const emailInput = Array.from(document.querySelectorAll("input")).find(isEmailInput);
    const passes = passwordInputs();
    if (!emailInput || passes.length < 1) return;
    if (emailInput.value !== state.email) nativeValue(emailInput, state.email);
    if (passes[0].value !== state.settings.password) nativeValue(passes[0], state.settings.password);

    if (state.submittedFor === "login" && Date.now() - state.lastSubmitAt < 20000) return;
    const submit = findButton(/^log ?in$/i);
    if (!submit || submit.disabled) return;
    state.submittedFor = "login";
    state.lastSubmitAt = Date.now();
    setStatus("Login otomatis...");
    submit.click();
  }

  function handleVerification() {
    if (!state.started) return;
    setStatus(`Cek inbox ${state.email}, klik link verifikasi. Setelah terverifikasi, helper lanjut otomatis.`);
    const success = /email confirmed|successfully confirmed|email verified|verification successful/i.test(document.body?.innerText || "");
    if (!success) return;
    const button = findButton(/continue|go to|start|open app/i);
    if (button) {
      button.click();
    } else {
      setTimeout(() => location.replace("/profileList"), 1200);
    }
  }

  function handleInstaller() {
    if (!state.started) return;
    if (!state.settings.skipInstaller) {
      if (state.settings.dismissPopups) clickByText(/^got it,? thanks!?$/i);
      return;
    }
    setStatus("Melewati halaman installer dan membatalkan download...");
    clickByText(/^got it,? thanks!?$/i);
    const skipped = clickByText(/^skip recommended setup$/i);
    if (skipped) state.lastActionAt = Date.now();
    if (Date.now() - state.lastActionAt > 2200) {
      state.lastActionAt = Date.now();
      location.replace("/profileList");
    }
  }

  function handleQuiz() {
    if (!state.started || !state.settings.autoQuiz) return;
    if (state.quizClicks >= 8) return;
    if (Date.now() - state.lastQuizClickAt < 1300) return;

    const options = Array.from(document.querySelectorAll("div")).filter((el) => {
      if (!visible(el)) return false;
      const style = getComputedStyle(el);
      if (style.cursor !== "pointer") return false;
      if (style.backgroundColor !== "rgb(12, 186, 151)" && style.backgroundColor !== "rgb(0, 169, 135)") return false;
      const text = textOf(el);
      if (!text || /back|download|install/i.test(text)) return false;
      return el.querySelector("svg, span");
    });

    const option = options[0];
    if (!option) return;
    state.quizClicks += 1;
    state.lastQuizClickAt = Date.now();
    setStatus(`Menyelesaikan onboarding quiz (${Math.min(state.quizClicks, 4)}/4)...`);
    option.click();
  }

  function closeOnboardingWall() {
    const marker = Array.from(document.querySelectorAll("div")).find(
      (el) => textOf(el) === "How do you want to run profiles?"
    );
    if (!marker) return false;
    let container = marker;
    for (let i = 0; i < 4 && container; i += 1) container = container.parentElement;
    if (!container) return false;
    const buttons = Array.from(container.querySelectorAll("button")).filter(visible);
    const close = buttons.find((button) => !textOf(button) && button.querySelector("svg"));
    if (!close) return false;
    close.click();
    setStatus("Menutup modal onboarding...");
    return true;
  }

  function closeCookieBanner() {
    const selectors = [
      "#CybotCookiebotDialogBodyButtonDecline",
      "#CybotCookiebotDialogBodyButtonAccept",
      'button[aria-label="Deny"]',
      'button[aria-label="Close"]'
    ];
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && visible(el)) {
        el.click();
        return true;
      }
    }
    return clickByText(/^(deny|only necessary|reject all|decline)$/i);
  }

  function closeGenericDialogs() {
    if (clickByText(/^maybe later$/i)) return true;
    if (clickByText(/^got it,? thanks!?$/i)) return true;
    if (clickByText(/^continue without setup$/i)) return true;
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible);
    for (const dialog of dialogs) {
      const close = Array.from(dialog.querySelectorAll("button")).find(
        (button) => visible(button) && (/^close$/i.test(textOf(button)) || /close/i.test(button.getAttribute("aria-label") || ""))
      );
      if (close) {
        close.click();
        return true;
      }
    }
    return false;
  }

  function dismissPopups() {
    if (!state.settings.dismissPopups) return;
    if (Date.now() - state.lastPopupSweepAt < 900) return;
    state.lastPopupSweepAt = Date.now();
    if (closeOnboardingWall()) return;
    if (closeCookieBanner()) return;
    closeGenericDialogs();
  }

  function isInstallerLink(value) {
    return /dl\.gologin\.com|dld\.gologin\.com|gologin-mini-inst|gologin-installer/i.test(value || "");
  }

  document.addEventListener(
    "click",
    (event) => {
      if (!state.settings.blockDownloads) return;
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const closest = target.closest("a,button,[role=button],span,div");
      const label = closest ? textOf(closest) : "";
      const href = closest?.closest?.("a")?.href || closest?.getAttribute?.("href") || "";
      const installerAction =
        /download manually|download & install|download and install|install gologin/i.test(label) ||
        isInstallerLink(href);
      if (!installerAction) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      setStatus("Download installer GoLogin dicegah.");
    },
    true
  );

  async function handleProxy() {
    if (!state.started || state.proxyDone) return;
    if (!state.proxyStartedAt) state.proxyStartedAt = Date.now();

    const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
    if (boxes.length < 2) {
      if (Date.now() - state.proxyStartedAt > 30000) {
        state.proxyDone = true;
        state.finalMessage = "Selesai. Tidak ada proxy di halaman ini.";
        await stopRun(state.finalMessage);
      } else {
        setStatus("Menunggu daftar proxy...");
      }
      return;
    }

    const selectAll = document.querySelector('input[aria-label="Select all"]');
    if (selectAll && !selectAll.checked) {
      const wrapper = selectAll.closest(".ant-checkbox") || selectAll.parentElement;
      wrapper.click();
      setStatus("Memilih semua proxy...");
      return;
    }
    if (boxes.some((box) => !box.checked)) {
      setStatus("Menunggu semua proxy terpilih...");
      return;
    }

    if (state.proxyCopying) {
      if (Date.now() - state.lastProxyActionAt < 3000) return;
      state.proxyCopying = false;
    }

    const copy = Array.from(document.querySelectorAll("span,button")).find(
      (el) => /^copy proxy$/i.test(textOf(el))
    );
    if (!copy) {
      setStatus("Tombol Copy proxy tidak ditemukan.");
      return;
    }

    state.proxyCopying = true;
    state.lastProxyActionAt = Date.now();
    document.documentElement.removeAttribute("data-gl-clipboard");
    copy.click();
    setStatus("Menyalin list proxy...");

    setTimeout(async () => {
      const text = document.documentElement.dataset.glClipboard || "";
      if (!text.includes("://")) {
        state.proxyCopying = false;
        setStatus("Menunggu hasil copy proxy...");
        return;
      }
      const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
      await chrome.storage.local.set({ proxyList: text, proxyCount: lines.length });
      showProxyList(text, lines.length);
      try {
        await regenerateEmail();
      } catch (err) {
        // Email lama tetap dipakai jika storage gagal
      }
      state.proxyDone = true;
      state.proxyCopying = false;
      state.finalMessage = `Selesai. ${lines.length} proxy tersimpan. Email baru disiapkan.`;
      await stopRun(state.finalMessage);
    }, 900);
  }

  async function routeLoop() {
    if (!state.settings.enabled) {
      setStatus("Helper nonaktif.");
      return;
    }
    if (!state.started) {
      setStatus(state.finalMessage || "Klik Start untuk mulai dari halaman signup.");
      return;
    }

    const path = location.pathname;
    if (path !== state.route) {
      state.route = path;
      state.quizClicks = 0;
      state.lastQuizClickAt = 0;
      state.lastActionAt = 0;
      state.signupFilledAt = 0;
      state.submittedFor = "";
      if (path === "/proxy") state.proxyStartedAt = Date.now();
    }

    if (path === "/sign_up" || path === "/sign_up_frame") {
      await handleSignup();
    } else if (path === "/sign_in") {
      await handleLogin();
    } else if (path === "/email_verification") {
      handleVerification();
    } else if (path === "/quiz") {
      handleQuiz();
    } else if (path === "/download-installer" || path === "/download") {
      handleInstaller();
    } else if (path === "/proxy") {
      await handleProxy();
    } else {
      setStatus("Masuk menu utama, membuka halaman proxy...");
      location.replace("/proxy");
    }

    if (path !== "/sign_up" && path !== "/sign_up_frame") dismissPopups();
  }

  async function boot() {
    await loadSettings();
    chrome.storage.onChanged.addListener(async (changes, area) => {
      if (area === "sync") {
        await loadSettings();
        return;
      }
      if (area === "local") {
        if (changes.generatedEmail) state.email = changes.generatedEmail.newValue || state.email;
        if (changes.password) state.settings.password = changes.password.newValue || state.settings.password;
        if (changes.signupUsed) state.signupUsed = !!changes.signupUsed.newValue;
        updateHud();
      }
    });
    setInterval(routeLoop, 700);
    routeLoop();
  }

  boot();
})();

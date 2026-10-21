(() => {
  const root = document.documentElement;
  if (!root) return;

  try {
    const clipboard = navigator.clipboard;
    if (clipboard && typeof clipboard.writeText === "function") {
      const original = clipboard.writeText.bind(clipboard);
      clipboard.writeText = async (text) => {
        root.dataset.glClipboard = String(text);
        return original(text);
      };
    }
  } catch (error) {
    void error;
  }

  document.addEventListener(
    "copy",
    () => {
      const selected = window.getSelection()?.toString();
      if (selected) root.dataset.glClipboard = selected;
    },
    true
  );

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || typeof data !== "object") return;

    if (data.type === "show-captcha" || data.type === "hcaptcha-challenge-opened") {
      root.dataset.glCaptchaVisible = "1";
      return;
    }

    if (data.type !== "captcha-result" && data.type !== "hcaptcha-success") return;

    const token = data.message?.captchaToken || data.captchaToken;
    if (!token) return;
    root.dataset.glCaptchaToken = String(token);
  });
})();

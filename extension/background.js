const DEFAULTS = { blockDownloads: true };

let settings = { ...DEFAULTS };

chrome.storage.sync.get(DEFAULTS, (value) => {
  settings = { ...settings, ...value };
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  for (const [key, change] of Object.entries(changes)) {
    if (key in settings) settings[key] = change.newValue;
  }
});

const INSTALLER_NAME = /gologin|orbita|gologin-mini-inst/i;
const ARCHIVE_EXT = /\.(exe|msi|dmg|pkg|deb|rpm|appimage|zip)(\?|#|$)/i;
const INSTALLER_URL = /dl\.gologin\.com|dld\.gologin\.com|gologin-mini-inst|gologin-installer/i;

function isInstaller(item) {
  const haystack = [item.filename, item.url, item.finalUrl, item.referrer]
    .filter(Boolean)
    .join(" ");
  if (INSTALLER_URL.test(haystack)) return true;
  return INSTALLER_NAME.test(haystack) && ARCHIVE_EXT.test(haystack);
}

chrome.downloads.onCreated.addListener((item) => {
  if (!settings.blockDownloads) return;
  if (!isInstaller(item)) return;
  chrome.downloads.cancel(item.id, () => {
    chrome.downloads.erase({ id: item.id });
  });
});

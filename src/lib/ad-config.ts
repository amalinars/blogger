/**
 * Ad & Monetization Configuration
 * Prepared for Monetag (PropellerAds) integration.
 */

export const MONETAG_CONFIG = {
  // Zone ID Service Worker dari sw.js
  zoneId: '12088388',
  domain: '3nbf4.com',
  // Multitag All-in-One
  multitag: {
    scriptSrc: 'https://quge5.com/88/tag.min.js',
    zone: '299712'
  },
  // Direct Link / Smartlink dari Monetag
  directLinkUrl: 'https://uplcm.com/4/12092846',
  // URL script Monetag Service Worker
  scriptSrc: 'https://3nbf4.com/act/files/service-worker.min.js?r=sw',
  // In-Page Push / Vignette / OnClick zone settings
  zones: {
    inPagePush: '',
    vignette: '',
    popunder: '',
    directLink: '12092846'
  }
} as const;

// Backward-compatible structure
export const AD_CONFIG = {
  leaderboard_728x90: { key: '', width: 728, height: 90 },
  banner_320x50: { key: '', width: 320, height: 50 },
  banner_468x60: { key: '', width: 320, height: 50 },
  rectangle_300x250: { key: '', width: 300, height: 250 },
  skyscraper_160x600: { key: '', width: 160, height: 600 },
  vertical_160x300: { key: '', width: 160, height: 300 },
  native_banner: { scriptSrc: '', containerId: '' },
  smartlink: { url: 'https://uplcm.com/4/12092846', pool: ['https://uplcm.com/4/12092846'] },
  social_bar: { scriptSrc: '' },
  popunder: { scriptSrc: '' }
} as const;

export function getRandomSmartlink(): string {
  return MONETAG_CONFIG.directLinkUrl || '';
}


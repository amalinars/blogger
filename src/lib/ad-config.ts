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
    popunder: {
      zone: '12092686',
      scriptSrc: 'https://al5sm.com/tag.min.js'
    },
    inPagePush: {
      zone: '12093786',
      scriptSrc: 'https://nap5k.com/tag.min.js'
    },
    vignette: {
      zone: '12093787',
      scriptSrc: 'https://n6wxm.com/vignette.min.js'
    },
    directLink: '12092846'
  }
} as const;

export const HILLTOPADS_CONFIG = {
  banner_300x250: {
    scriptSrc: '//simplistic-walk.com/bSXRV.sLd/GTlM0mYfWDcH/Oe-m/9iuPZ/U/l/kwPKTVcF1yNPDBEFwHMCDYEBt/NBzCUt0EMBTzAywuNYQB',
    referrerPolicy: 'no-referrer-when-downgrade'
  },
  popunder: {
    scriptSrc: '//direct-league.com/crDU9D6Mb.2k5XliSEWGQB9sNPzKU_0/MhT/AQyGNKS/0x3JNCT-Q-xMM/D/Is5c',
    referrerPolicy: 'no-referrer-when-downgrade'
  },
  directLinkUrl: 'https://gullible-thanks.com/O8pqAQ'
} as const;

export function getStepDirectLink(step: number = 1): { url: string; label: string } {
  // Odd steps (1, 3): Monetag
  // Even steps (2, 4): HilltopAds
  if (step % 2 === 0 && HILLTOPADS_CONFIG.directLinkUrl) {
    return {
      url: HILLTOPADS_CONFIG.directLinkUrl,
      label: 'Hilltop High-Speed Sponsor Mirror'
    };
  }
  return {
    url: MONETAG_CONFIG.directLinkUrl || HILLTOPADS_CONFIG.directLinkUrl,
    label: 'Monetag Fast Direct Mirror'
  };
}

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


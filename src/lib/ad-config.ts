/**
 * Ad & Monetization Configuration
 * Dedicated to A-Ads (Anonymous Ads) & HilltopAds
 */

export const AADS_CONFIG = {
  fixedCenter: {
    unitId: '2459425',
    iframeSrc: '//acceptable.a-ads.com/2459425/?size=Adaptive'
  },
  stickyTop: {
    unitId: '2459431',
    iframeSrc: '//acceptable.a-ads.com/2459431/?size=Adaptive'
  },
  stickyLeft: {
    unitId: '2459432',
    iframeSrc: '//acceptable.a-ads.com/2459432/?size=Adaptive'
  },
  stickyRight: {
    unitId: '2459433',
    iframeSrc: '//acceptable.a-ads.com/2459433/?size=Adaptive'
  },
  stickyBottom: {
    unitId: '2459434',
    iframeSrc: '//acceptable.a-ads.com/2459434/?size=Adaptive'
  },
  // Legacy alias for single unit
  unitId: '2459425',
  iframeSrc: '//acceptable.a-ads.com/2459425/?size=Adaptive'
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
  return {
    url: HILLTOPADS_CONFIG.directLinkUrl,
    label: 'High-Speed Sponsor Mirror'
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
  smartlink: { url: HILLTOPADS_CONFIG.directLinkUrl, pool: [HILLTOPADS_CONFIG.directLinkUrl] },
  social_bar: { scriptSrc: '' },
  popunder: { scriptSrc: '' }
} as const;

export function getRandomSmartlink(): string {
  return HILLTOPADS_CONFIG.directLinkUrl;
}

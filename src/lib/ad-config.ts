export const AD_CONFIG = {
  leaderboard_728x90: {
    key: '88bde01fe9026b0d9b5560034c4356c0',
    width: 728,
    height: 90
  },
  banner_320x50: {
    key: '476430ceaf959fb4ad9568c20deb82d7',
    width: 320,
    height: 50
  },
  banner_468x60: {
    key: '476430ceaf959fb4ad9568c20deb82d7',
    width: 320,
    height: 50
  },
  rectangle_300x250: {
    key: '415d8f54aa34535e296d8a4c9a8f381f',
    width: 300,
    height: 250
  },
  skyscraper_160x600: {
    key: 'c03a94caf7345df03cbb8a148ca5884b',
    width: 160,
    height: 600
  },
  vertical_160x300: {
    key: '0c14e1df9546556b892f8c2756b2c9f5',
    width: 160,
    height: 300
  },
  native_banner: {
    scriptSrc: 'https://bauval.org/21/8f8649988daccf25980ae3acc0b44d07',
    containerId: 'container-8f8649988daccf25980ae3acc0b44d07'
  },
  smartlink: {
    url: 'https://www.profitableratecpmnetwork.com/wfbxac2hpn?key=49e072f6e7743835ebfbaa0961eff226',
    pool: [
      { id: 31819973, name: 'Smartlink Active 1', url: 'https://www.profitableratecpmnetwork.com/wfbxac2hpn?key=49e072f6e7743835ebfbaa0961eff226', category: 'mainstream' }
    ]
  },
  social_bar: {
    scriptSrc: 'https://bauval.org/14/d1b08f4dfc08883f7373da4a28f604b2'
  },
  popunder: {
    scriptSrc: 'https://pl31920470.profitableratecpmnetwork.com/49/c7/ce/49c7cec8999e07745020694cb2ce20e2.js'
  }
} as const;

export function getRandomSmartlink(allowAdult: boolean = true): string {
  const pool = allowAdult
    ? AD_CONFIG.smartlink.pool
    : AD_CONFIG.smartlink.pool.filter((s) => s.category === 'mainstream');
  if (pool.length === 0) return AD_CONFIG.smartlink.url;
  const randomIndex = Math.floor(Math.random() * pool.length);
  return pool[randomIndex].url;
}

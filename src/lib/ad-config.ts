export const AD_CONFIG = {
  leaderboard_728x90: {
    key: '046e9297bac233358f2f95ec49c18280',
    width: 728,
    height: 90
  },
  banner_468x60: {
    key: '3adad5381763d6382636069608f47a89',
    width: 468,
    height: 60
  },
  rectangle_300x250: {
    key: '557638ee74e336cb8d9fac4b22f5c91a',
    width: 300,
    height: 250
  },
  skyscraper_160x600: {
    key: 'a2f22aef5af4a5a5d67177c9212f7ecc',
    width: 160,
    height: 600
  },
  vertical_160x300: {
    key: '940a195a3601266cfd9f0ba35edd8395',
    width: 160,
    height: 300
  },
  native_banner: {
    scriptSrc: 'https://bauval.org/21/1e05a42e74ceef86af862833db1dc002',
    containerId: 'container-1e05a42e74ceef86af862833db1dc002'
  },
  smartlink: {
    url: 'https://www.profitableratecpmnetwork.com/wfbxac2hpn?key=49e072f6e7743835ebfbaa0961eff226',
    pool: [
      { id: 31819973, name: 'Smartlink 1', url: 'https://www.profitableratecpmnetwork.com/wfbxac2hpn?key=49e072f6e7743835ebfbaa0961eff226', category: 'mainstream' },
      { id: 23272149, name: 'DirectLink 1', url: 'https://www.profitableratecpmnetwork.com/qwc4w81bj?key=c70e184404d856cce251b250f3c58bbc', category: 'mainstream' },
      { id: 31819971, name: 'Popunder Direct', url: 'https://www.profitableratecpmnetwork.com/app4z7qd9?key=49c7cec8999e07745020694cb2ce20e2', category: 'mainstream' }
    ]
  },
  social_bar: {
    scriptSrc: 'https://bauval.org/14/221b8ac1e62e1ea2e1c6c8bcdf06a26e'
  },
  popunder: {
    scriptSrc: 'https://www.profitableratecpmnetwork.com/49c7cec8999e07745020694cb2ce20e2/invoke.js'
  }
} as const;

export function getRandomSmartlink(allowAdult: boolean = true): string {
  const pool = allowAdult
    ? AD_CONFIG.smartlink.pool
    : AD_CONFIG.smartlink.pool.filter((s) => s.category === 'mainstream');
  const randomIndex = Math.floor(Math.random() * pool.length);
  return pool[randomIndex].url;
}

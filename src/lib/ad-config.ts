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
    url: 'https://araplhn.org/4/3714e867534d8e967cc514e3fe1e1f86',
    pool: [
      { id: 31673390, name: 'Blog Smartlink', url: 'https://araplhn.org/4/3714e867534d8e967cc514e3fe1e1f86', category: 'mainstream' },
      { id: 31673376, name: 'Smartlink 1', url: 'https://asiafilm.org/4/7eac5b9300b22ac99ca80c8cdb6b3bcd', category: 'mainstream' },
      { id: 31809735, name: 'Smartlink 2', url: 'https://asiafilm.org/4/25bc1d535da8f9230c12c507135632df', category: 'mainstream' },
      { id: 31809819, name: 'Smartlink 3', url: 'https://auctionr.org/4/5740ecd138a8347bdcfb133ada0e7c94', category: 'adult' },
      { id: 31809827, name: 'Smartlink 4', url: 'https://asiafilm.org/4/345ccd961a9780f5ab49ebc64d853bd0', category: 'mainstream' },
      { id: 31809832, name: 'Smartlink 5', url: 'https://asiafilm.org/4/798a138996d8c9994d4f8e2aea0b738f', category: 'mainstream' }
    ]
  },
  social_bar: {
    scriptSrc: 'https://bauval.org/14/221b8ac1e62e1ea2e1c6c8bcdf06a26e'
  },
  popunder: {
    scriptSrc: 'https://abscloud.org/1/1ebdef2912aa634d2b91cca5ae7f6405'
  }
} as const;

export function getRandomSmartlink(allowAdult: boolean = true): string {
  const pool = allowAdult
    ? AD_CONFIG.smartlink.pool
    : AD_CONFIG.smartlink.pool.filter((s) => s.category === 'mainstream');
  const randomIndex = Math.floor(Math.random() * pool.length);
  return pool[randomIndex].url;
}

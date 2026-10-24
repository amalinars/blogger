export const ADSTERRA = {
  socialBarSrc: 'https://bauval.org/14/4003659bb47be99b45e78647148ee214',
  smartLinkSrc: 'https://araplhn.org/4/57ef1d1efc44d84ac528753127e75892',
  nativeBannerSrc: 'https://bauval.org/21/eff1cc809a63f65a58e6ad5541eb7757',
  nativeBannerContainerId: 'container-eff1cc809a63f65a58e6ad5541eb7757',
} as const;

export type BannerAd = {
  key: string;
  width: number;
  height: number;
  src: string;
};

export const ADSTERRA_BANNERS: BannerAd[] = [
  { key: '3754ab49e0a5b1f8f81e3eeda1072253', width: 468, height: 60, src: 'https://bauval.org/22/3754ab49e0a5b1f8f81e3eeda1072253' },
  { key: '08b37a303da759d0a288b118afb36461', width: 300, height: 250, src: 'https://bauval.org/22/08b37a303da759d0a288b118afb36461' },
  { key: 'd0b5705874d761face94c9256b363239', width: 160, height: 300, src: 'https://bauval.org/22/d0b5705874d761face94c9256b363239' },
  { key: 'e584ed527b6d359792e3ba7b31a72e81', width: 160, height: 600, src: 'https://bauval.org/22/e584ed527b6d359792e3ba7b31a72e81' },
  { key: 'd9935415a4852bac675ddd443e9703e6', width: 320, height: 50, src: 'https://bauval.org/22/d9935415a4852bac675ddd443e9703e6' },
  { key: '925bef0b35c839b5eb1b87f6b0569c3c', width: 728, height: 90, src: 'https://bauval.org/22/925bef0b35c839b5eb1b87f6b0569c3c' },
];

// Named positions for layout placement
export const BANNER_LEADERBOARD  = ADSTERRA_BANNERS[5]; // 728x90  – below header
export const BANNER_HALF_BANNER  = ADSTERRA_BANNERS[0]; // 468x60  – right col top
export const BANNER_MED_RECT     = ADSTERRA_BANNERS[1]; // 300x250 – left sidebar
export const BANNER_SKYSCRAPER   = ADSTERRA_BANNERS[3]; // 160x600 – left sidebar
export const BANNER_MOBILE       = ADSTERRA_BANNERS[4]; // 320x50  – right col bottom
export const BANNER_HALF_PAGE    = ADSTERRA_BANNERS[2]; // 160x300 – right col bottom


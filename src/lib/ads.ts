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

// Active high-performing placements:
export const BANNER_LEADERBOARD  = ADSTERRA_BANNERS[5]; // 728x90  – below header (top earner)
export const BANNER_MED_RECT     = ADSTERRA_BANNERS[1]; // 300x250 – left sidebar
export const BANNER_SKYSCRAPER   = ADSTERRA_BANNERS[3]; // 160x600 – left sidebar

// Adsterra Links & Scripts
export const ADSTERRA_SMARTLINK = 'https://araplhn.org/4/57ef1d1efc44d84ac528753127e75892';
export const ADSTERRA_POPUNDER_SRC = 'https://abscloud.org/1/eeed8343b7ddf3fe3051d2f96d96108d';
export const ADSTERRA_SOCIALBAR_SRC = 'https://bauval.org/14/4003659bb47be99b45e78647148ee214';

// Monetag Links & Scripts
export const MONETAG_DIRECT_LINK = 'https://uplcm.com/4/12124796';
export const MONETAG_MULTITAG_SRC = 'https://quge5.com/88/tag.min.js';
export const MONETAG_MULTITAG_ZONE = '302175';

// Ad Provider split (Adsterra / Monetag / Both)
export type AdProvider = 'adsterra' | 'monetag';

export function getAdProvider(): AdProvider {
  if (typeof window === 'undefined') return 'adsterra';

  try {
    // 1. Prioritaskan parameter URL (?ad_network=monetag | adsterra | both)
    const urlParams = new URLSearchParams(window.location.search);
    const param = (urlParams.get('ad_network') || urlParams.get('ad_provider') || '').toLowerCase();

    if (param === 'monetag') {
      window.sessionStorage.setItem('ad_provider', 'monetag');
      return 'monetag';
    }
    if (param === 'adsterra') {
      window.sessionStorage.setItem('ad_provider', 'adsterra');
      return 'adsterra';
    }
    if (param === 'both' || param === 'hybrid' || param === 'auto') {
      const assigned: AdProvider = Math.random() < 0.5 ? 'adsterra' : 'monetag';
      window.sessionStorage.setItem('ad_provider', assigned);
      return assigned;
    }

    // 2. Cek sessionStorage yang sudah tersimpan sebelumnya
    const cached = window.sessionStorage.getItem('ad_provider') as AdProvider | null;
    if (cached === 'adsterra' || cached === 'monetag') {
      return cached;
    }

    // 3. Default fallback: rotasi 50% Adsterra / 50% Monetag
    const assigned: AdProvider = Math.random() < 0.5 ? 'adsterra' : 'monetag';
    window.sessionStorage.setItem('ad_provider', assigned);
    return assigned;
  } catch {
    return 'adsterra';
  }
}

export function getActiveSmartlink(): string {
  const provider = getAdProvider();
  return provider === 'monetag' ? MONETAG_DIRECT_LINK : ADSTERRA_SMARTLINK;
}

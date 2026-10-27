'use client';

import { useEffect, useRef, useState } from 'react';
import type { BannerAd } from '@/lib/ads';
import { getAdProvider, AdProvider, EXOCLICK_BANNER_ZONE_ID, serveExoClick } from '@/lib/ads';

// All BannerSlot instances share one promise chain so atOptions is never
// overwritten before the previous Adsterra script has finished executing.
let bannerQueue: Promise<void> = Promise.resolve();

function enqueue(loader: () => Promise<void>): Promise<void> {
  bannerQueue = bannerQueue.then(loader, loader);
  return bannerQueue;
}

type BannerSlotProps = {
  banner: BannerAd;
  className?: string;
};

export function BannerSlot({ banner, className = '' }: BannerSlotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const [provider, setProvider] = useState<AdProvider>(() =>
    typeof window !== 'undefined' ? getAdProvider() : 'adsterra'
  );

  useEffect(() => {
    const currentProvider = getAdProvider();
    setProvider(currentProvider);

    const el = ref.current;
    if (!el || started.current) return;
    started.current = true;

    if (currentProvider === 'exoclick') {
      serveExoClick();
      return;
    }

    enqueue(
      () =>
        new Promise<void>((resolve) => {
          (window as unknown as Record<string, unknown>)['atOptions'] = {
            key: banner.key,
            format: 'iframe',
            height: banner.height,
            width: banner.width,
            params: {},
          };

          const script = document.createElement('script');
          script.src = banner.src;
          script.async = false;
          script.dataset.cfasync = 'false';
          script.onload = () => resolve();
          script.onerror = () => resolve();
          el.appendChild(script);
        }),
    );
  }, [banner]);

  if (provider === 'exoclick') {
    // Tampilkan banner di Leaderboard (atas) dan Medium Rectangle (sidebar).
    // Sembunyikan untuk Skyscraper (160x600) agar layout sidebar tetap rapi dan proporsional.
    if (banner.height > 300 && banner.width <= 200) {
      return null;
    }

    return (
      <div
        ref={ref}
        className={`flex justify-center overflow-hidden rounded-2xl border border-line bg-surface-raised p-3 transition-all duration-300 ${className}`}
      >
        <ins className="eas6a97888e2" data-zoneid={String(EXOCLICK_BANNER_ZONE_ID)} />
      </div>
    );
  }

  return (
    <div
      ref={ref}
      id={`container-${banner.key}`}
      className={`flex justify-center overflow-hidden ${className}`}
      style={{ minHeight: banner.height }}
    />
  );
}

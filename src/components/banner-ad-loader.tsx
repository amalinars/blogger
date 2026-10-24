'use client';

import { useEffect, useRef } from 'react';
import type { BannerAd } from '@/lib/ads';

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

  useEffect(() => {
    const el = ref.current;
    if (!el || started.current) return;
    started.current = true;

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

  return (
    <div
      ref={ref}
      id={`container-${banner.key}`}
      className={`flex justify-center overflow-hidden ${className}`}
      style={{ minHeight: banner.height }}
    />
  );
}

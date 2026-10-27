'use client';

import { useEffect, useRef, useState } from 'react';
import { getAdProvider, AdProvider, EXOCLICK_BANNER_ZONE_ID, serveExoClick } from '@/lib/ads';

type BannerSlotProps = {
  className?: string;
  height?: number;
  width?: number;
};

export function BannerSlot({ className = '', height = 90, width = 728 }: BannerSlotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const [provider, setProvider] = useState<AdProvider>(() =>
    typeof window !== 'undefined' ? getAdProvider() : 'monetag'
  );

  useEffect(() => {
    const currentProvider = getAdProvider();
    setProvider(currentProvider);

    const el = ref.current;
    if (!el || started.current) return;
    started.current = true;

    if (currentProvider === 'exoclick') {
      serveExoClick();
    }
  }, []);

  if (provider === 'exoclick') {
    if (height > 300 && width <= 200) {
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

  return null;
}

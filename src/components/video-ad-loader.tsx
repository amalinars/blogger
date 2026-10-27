'use client';

import { useEffect, useRef, useState } from 'react';
import { getAdProvider, AdProvider, EXOCLICK_OUTSTREAM_ZONE_ID, serveExoClick } from '@/lib/ads';

declare global {
  interface Window {
    AdProvider?: any[];
  }
}

export function VideoAdSlot({ className = '' }: { className?: string }) {
  const [provider, setProvider] = useState<AdProvider>(() =>
    typeof window !== 'undefined' ? getAdProvider() : 'monetag'
  );
  const loaded = useRef(false);

  useEffect(() => {
    const currentProvider = getAdProvider();
    setProvider(currentProvider);

    if (loaded.current) return;
    loaded.current = true;

    if (currentProvider === 'exoclick') {
      serveExoClick();
    }
  }, []);

  if (provider !== 'exoclick') {
    return null;
  }

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-line bg-surface-raised p-4 transition-all duration-300 shadow-sm ${className}`}
    >
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2.5">
        <span className="font-code text-[10px] uppercase tracking-[0.16em] text-faint flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse" />
          Featured Video
        </span>
        <span className="rounded bg-surface-2 px-2 py-0.5 font-code text-[9px] uppercase tracking-wider text-muted">
          Sponsored
        </span>
      </div>

      <div className="min-h-[160px] w-full flex justify-center items-center overflow-hidden">
        <ins className="eas6a97888e37" data-zoneid={String(EXOCLICK_OUTSTREAM_ZONE_ID)} />
      </div>
    </div>
  );
}

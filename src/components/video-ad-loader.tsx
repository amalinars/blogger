'use client';

import { useEffect, useRef, useState } from 'react';
import { getAdProvider, AdProvider, EXOCLICK_NATIVE_SCRIPT, EXOCLICK_OUTSTREAM_ZONE_ID } from '@/lib/ads';

declare global {
  interface Window {
    AdProvider?: any[];
  }
}

export function VideoAdSlot({ className = '' }: { className?: string }) {
  const [provider, setProvider] = useState<AdProvider>('adsterra');
  const loaded = useRef(false);

  useEffect(() => {
    const currentProvider = getAdProvider();
    setProvider(currentProvider);

    if (loaded.current) return;
    loaded.current = true;

    if (currentProvider === 'exoclick') {
      // Ensure AdProvider script is initialized
      if (!document.getElementById('exoclick-native-script')) {
        const script = document.createElement('script');
        script.id = 'exoclick-native-script';
        script.async = true;
        script.type = 'application/javascript';
        script.src = EXOCLICK_NATIVE_SCRIPT;
        script.onload = () => {
          try {
            (window.AdProvider = window.AdProvider || []).push({ serve: {} });
          } catch {}
        };
        document.body.appendChild(script);
      } else {
        try {
          (window.AdProvider = window.AdProvider || []).push({ serve: {} });
        } catch {}
      }
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

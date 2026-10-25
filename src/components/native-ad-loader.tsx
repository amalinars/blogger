'use client';

import { useEffect, useRef } from 'react';

export function NativeAdSlot({ className = '' }: { className?: string }) {
  const loaded = useRef(false);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;

    // Load Adsterra Native Banner script
    const script = document.createElement('script');
    script.async = true;
    script.setAttribute('data-cfasync', 'false');
    script.src = 'https://bauval.org/21/eff1cc809a63f65a58e6ad5541eb7757';
    document.body.appendChild(script);
  }, []);

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-line bg-surface-raised p-4 transition-all duration-300 ${className}`}
    >
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2.5">
        <span className="font-code text-[10px] uppercase tracking-[0.16em] text-faint">
          Recommended Content
        </span>
        <span className="rounded bg-surface-2 px-2 py-0.5 font-code text-[9px] uppercase tracking-wider text-muted">
          Sponsored
        </span>
      </div>
      <div
        id="container-eff1cc809a63f65a58e6ad5541eb7757"
        className="min-h-[140px] w-full"
      />
    </div>
  );
}

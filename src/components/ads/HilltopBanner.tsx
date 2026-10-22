'use client';

import React, { useEffect, useRef } from 'react';

interface HilltopBannerProps {
  className?: string;
  label?: string;
}

export function HilltopBanner({
  className = '',
  label = 'Sponsored Advertisement'
}: HilltopBannerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Reset container to avoid duplicate scripts on hot reloads
    el.innerHTML = '';

    const script = document.createElement('script');
    script.src = '//simplistic-walk.com/bSXRV.sLd/GTlM0mYfWDcH/Oe-m/9iuPZ/U/l/kwPKTVcF1yNPDBEFwHMCDYEBt/NBzCUt0EMBTzAywuNYQB';
    script.async = true;
    script.referrerPolicy = 'no-referrer-when-downgrade';

    el.appendChild(script);
  }, []);

  return (
    <div className={`flex flex-col items-center justify-center my-4 ${className}`}>
      {label && (
        <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 dark:text-neutral-500 mb-1.5 block">
          {label}
        </span>
      )}
      <div
        ref={containerRef}
        className="w-[300px] min-h-[250px] bg-neutral-100/50 dark:bg-neutral-900/40 rounded-xl flex items-center justify-center overflow-hidden border border-dashed border-neutral-300 dark:border-neutral-800 shadow-sm"
        data-ad-zone="hilltopads-300x250"
      />
    </div>
  );
}

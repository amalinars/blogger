'use client';

import React, { useEffect, useRef } from 'react';
import { AD_CONFIG } from '@/lib/ad-config';

export function NativeBanner() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Check if script already appended
    const scriptSrc = AD_CONFIG.native_banner.scriptSrc;
    const existingScript = containerRef.current.querySelector(`script[src="${scriptSrc}"]`);
    if (!existingScript) {
      const script = document.createElement('script');
      script.src = scriptSrc;
      script.async = true;
      script.setAttribute('data-cfasync', 'false');
      containerRef.current.appendChild(script);
    }
  }, []);

  return (
    <div className="my-10 w-full overflow-hidden" ref={containerRef}>
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-[10px] font-mono uppercase tracking-widest opacity-50"
          style={{ color: 'var(--text-muted)' }}
        >
          Sponsored Editorial Recommendations
        </span>
        <span
          className="text-[9px] font-mono opacity-30"
          style={{ color: 'var(--text-faint)' }}
        >
          Adsterra Native
        </span>
      </div>

      <div
        className="rounded-xl border border-dashed p-4 min-h-[140px] flex items-center justify-center"
        style={{
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-card)'
        }}
      >
        <div id={AD_CONFIG.native_banner.containerId} className="w-full text-center"></div>
      </div>
    </div>
  );
}

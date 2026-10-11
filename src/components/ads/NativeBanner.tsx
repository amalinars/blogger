'use client';

import React, { useEffect, useRef } from 'react';

export function NativeBanner() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Check if script already appended
    const existingScript = containerRef.current.querySelector('script[src*="1e05a42e74ceef86af862833db1dc002"]');
    if (!existingScript) {
      const script = document.createElement('script');
      script.src = 'https://bauval.org/21/1e05a42e74ceef86af862833db1dc002';
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
        <div id="container-1e05a42e74ceef86af862833db1dc002" className="w-full text-center"></div>
      </div>
    </div>
  );
}

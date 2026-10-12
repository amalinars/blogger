'use client';

import React, { useState, useEffect } from 'react';

interface AdBannerProps {
  adKey: string;
  width: number;
  height: number;
  className?: string;
  label?: string;
  autoRefresh?: boolean;
  refreshInterval?: number; // in seconds
}

export function AdBanner({
  adKey,
  width,
  height,
  className = '',
  label = 'Sponsored Advertisement',
  autoRefresh = true,
  refreshInterval = 35
}: AdBannerProps) {
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!autoRefresh || refreshInterval <= 0) return;

    const interval = setInterval(() => {
      // Only refresh if tab is currently active to preserve impressions quality and bandwidth
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        setRefreshKey((prev) => prev + 1);
      }
    }, refreshInterval * 1000);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  // srcDoc encapsulates atOptions and prevents collisions between multiple ad slots
  const srcDoc = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          * { margin: 0; padding: 0; box-sizing: border-box; }
          body {
            display: flex;
            justify-content: center;
            align-items: center;
            background: transparent;
            overflow: hidden;
            width: 100%;
            height: 100%;
          }
        </style>
      </head>
      <body>
        <script type="text/javascript">
          atOptions = {
            'key' : '${adKey}',
            'format' : 'iframe',
            'height' : ${height},
            'width' : ${width},
            'params' : {}
          };
        </script>
        <script type="text/javascript" src="https://bauval.org/22/${adKey}"></script>
        <!-- refresh #${refreshKey} -->
      </body>
    </html>
  `;

  return (
    <div className={`flex flex-col items-center justify-center my-6 overflow-hidden ${className}`}>
      {label && (
        <span
          className="text-[9px] font-mono uppercase tracking-widest mb-1.5 opacity-40 select-none flex items-center space-x-1"
          style={{ color: 'var(--text-muted)' }}
        >
          <span>{label}</span>
          {autoRefresh && (
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500/70 animate-pulse" title="Live Auto-Refreshed Ad Slot" />
          )}
        </span>
      )}
      <div
        className="overflow-hidden rounded-lg border border-dashed flex items-center justify-center transition-all duration-300"
        style={{
          width: `${width}px`,
          maxWidth: '100%',
          height: `${height}px`,
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-subtle)'
        }}
      >
        <iframe
          key={`${adKey}-${refreshKey}`}
          title={`ad-${adKey}-${refreshKey}`}
          srcDoc={srcDoc}
          width={width}
          height={height}
          style={{ border: 'none', overflow: 'hidden' }}
          scrolling="no"
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        />
      </div>
    </div>
  );
}

export { AD_CONFIG } from '@/lib/ad-config';

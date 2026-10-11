'use client';

import React from 'react';

interface AdBannerProps {
  adKey: string;
  width: number;
  height: number;
  className?: string;
  label?: string;
}

export function AdBanner({
  adKey,
  width,
  height,
  className = '',
  label = 'Sponsored Advertisement'
}: AdBannerProps) {
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
      </body>
    </html>
  `;

  return (
    <div className={`flex flex-col items-center justify-center my-6 overflow-hidden ${className}`}>
      {label && (
        <span
          className="text-[9px] font-mono uppercase tracking-widest mb-1.5 opacity-40 select-none"
          style={{ color: 'var(--text-muted)' }}
        >
          {label}
        </span>
      )}
      <div
        className="overflow-hidden rounded-lg border border-dashed flex items-center justify-center"
        style={{
          width: `${width}px`,
          maxWidth: '100%',
          height: `${height}px`,
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-subtle)'
        }}
      >
        <iframe
          title={`ad-${adKey}`}
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

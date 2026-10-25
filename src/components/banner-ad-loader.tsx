'use client';

import { useEffect, useRef } from 'react';
import type { BannerAd } from '@/lib/ads';

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

    // Create an isolated sandboxed iframe.
    // - allow-scripts & allow-same-origin: required by Adsterra to render the ad and execute ad scripts.
    // - allow-popups & allow-popups-to-escape-sandbox: allowed so legitimate user clicks can open the advertiser page in a new tab.
    // - NO allow-top-navigation: strictly prevents rogue ad scripts from hijacking/redirecting the main shortlink window.
    const iframe = document.createElement('iframe');
    iframe.width = `${banner.width}`;
    iframe.height = `${banner.height}`;
    iframe.style.width = `${banner.width}px`;
    iframe.style.height = `${banner.height}px`;
    iframe.style.border = 'none';
    iframe.style.overflow = 'hidden';
    iframe.style.backgroundColor = 'transparent';
    iframe.setAttribute('allowtransparency', 'true');
    iframe.scrolling = 'no';
    iframe.setAttribute(
      'sandbox',
      'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox'
    );

    el.appendChild(iframe);

    const doc = iframe.contentWindow?.document || iframe.contentDocument;
    if (doc) {
      doc.open();
      doc.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body {
              margin: 0;
              padding: 0;
              overflow: hidden;
              width: 100%;
              height: 100%;
              display: flex;
              justify-content: center;
              align-items: center;
              background-color: transparent !important;
            }
          </style>
        </head>
        <body>
          <script type="text/javascript">
            atOptions = {
              'key': '${banner.key}',
              'format': 'iframe',
              'height': ${banner.height},
              'width': ${banner.width},
              'params': {}
            };
          </script>
          <script type="text/javascript" src="${banner.src}"></script>
        </body>
        </html>
      `);
      doc.close();
    }
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

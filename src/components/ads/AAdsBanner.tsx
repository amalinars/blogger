'use client';

import React from 'react';
import { AADS_CONFIG } from '@/lib/ad-config';

interface AAdsBannerProps {
  className?: string;
  label?: string;
}

export function AAdsBanner({
  className = '',
  label = 'Sponsored Partner'
}: AAdsBannerProps) {
  return (
    <div className={`w-full flex flex-col items-center justify-center my-4 ${className}`}>
      {label && (
        <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 dark:text-neutral-500 mb-1.5 block">
          {label}
        </span>
      )}
      {/* BEGIN AADS AD UNIT 2459425 */}
      <div id="frame" style={{ width: '100%', margin: 'auto', position: 'relative', zIndex: 10 }}>
        <iframe
          data-aa={AADS_CONFIG.unitId}
          src={AADS_CONFIG.iframeSrc}
          style={{
            border: 0,
            padding: 0,
            width: '70%',
            minWidth: '280px',
            height: 'auto',
            minHeight: '60px',
            overflow: 'hidden',
            display: 'block',
            margin: 'auto'
          }}
          title="A-Ads Sponsor"
        />
      </div>
      {/* END AADS AD UNIT 2459425 */}
    </div>
  );
}

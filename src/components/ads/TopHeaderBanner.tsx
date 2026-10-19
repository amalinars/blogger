'use client';

import React from 'react';
import { AdBanner } from './AdBanner';
import { AD_CONFIG } from '@/lib/ad-config';

export function TopHeaderBanner() {
  return (
    <div
      className="w-full border-b py-3 flex flex-col items-center justify-center transition-all overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        borderColor: 'var(--border-subtle)'
      }}
      role="complementary"
      aria-label="Top Header Sponsored Slot"
    >
      <div className="max-w-7xl mx-auto px-2 sm:px-4 w-full flex flex-wrap justify-center items-center gap-4">
        {/* Leaderboard 728x90 - Always Active On All Resolutions */}
        <div className="flex justify-center max-w-full overflow-x-auto">
          <AdBanner
            adKey={AD_CONFIG.leaderboard_728x90.key}
            width={AD_CONFIG.leaderboard_728x90.width}
            height={AD_CONFIG.leaderboard_728x90.height}
            label="Header Leaderboard Dispatch"
            className="my-0"
            refreshInterval={25}
          />
        </div>

        {/* Medium Rectangle 300x250 - Always Active On All Resolutions */}
        <div className="flex justify-center max-w-full overflow-x-auto">
          <AdBanner
            adKey={AD_CONFIG.rectangle_300x250.key}
            width={AD_CONFIG.rectangle_300x250.width}
            height={AD_CONFIG.rectangle_300x250.height}
            label="Header Compact Dispatch"
            className="my-0"
            refreshInterval={25}
          />
        </div>
      </div>
    </div>
  );
}

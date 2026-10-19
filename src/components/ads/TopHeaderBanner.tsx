'use client';

import React from 'react';
import { AdBanner } from './AdBanner';
import { AD_CONFIG } from '@/lib/ad-config';

export function TopHeaderBanner() {
  return (
    <div
      className="w-full border-b py-2 sm:py-3 flex flex-col items-center justify-center transition-all overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        borderColor: 'var(--border-subtle)'
      }}
      role="complementary"
      aria-label="Top Header Sponsored Slot"
    >
      <div className="max-w-7xl mx-auto px-2 sm:px-4 w-full flex justify-center items-center">
        {/* Desktop / Tablet Leaderboard (728x90) */}
        <div className="hidden md:flex justify-center max-w-full">
          <AdBanner
            adKey={AD_CONFIG.leaderboard_728x90.key}
            width={AD_CONFIG.leaderboard_728x90.width}
            height={AD_CONFIG.leaderboard_728x90.height}
            label="Header Dispatch"
            className="my-0"
            autoRefresh={false}
          />
        </div>

        {/* Mobile Banner (320x50) */}
        <div className="flex md:hidden justify-center max-w-full">
          <AdBanner
            adKey={AD_CONFIG.banner_320x50.key}
            width={AD_CONFIG.banner_320x50.width}
            height={AD_CONFIG.banner_320x50.height}
            label="Sponsored Dispatch"
            className="my-0"
            autoRefresh={false}
          />
        </div>
      </div>
    </div>
  );
}

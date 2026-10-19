'use client';

import React, { useState } from 'react';
import { X, Sparkles } from 'lucide-react';
import { AdBanner } from './AdBanner';
import { AD_CONFIG } from '@/lib/ad-config';

export function StickyBottomBanner() {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 transition-all duration-300 animate-in fade-in slide-in-from-bottom-4"
      role="complementary"
      aria-label="Floating Sponsored Banner"
    >
      <div
        className="w-full border-t shadow-2xl backdrop-blur-md py-2 px-3 sm:px-4"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-strong)',
          boxShadow: '0 -10px 25px -5px rgba(0, 0, 0, 0.1), 0 -8px 10px -6px rgba(0, 0, 0, 0.1)'
        }}
      >
        <div className="max-w-5xl mx-auto flex flex-col items-center relative">
          {/* Top meta bar with title & dismiss button */}
          <div className="w-full flex items-center justify-between pb-1 max-w-[740px]">
            <div className="flex items-center space-x-2 text-[10px] font-mono uppercase tracking-wider opacity-60" style={{ color: 'var(--text-muted)' }}>
              <Sparkles className="w-3 h-3 text-amber-600 dark:text-amber-400" />
              <span>Partner Dispatch • Live Rotation</span>
            </div>

            <button
              onClick={() => setDismissed(true)}
              className="p-1 rounded-md text-xs font-mono opacity-50 hover:opacity-100 transition-opacity flex items-center space-x-1 cursor-pointer"
              style={{ color: 'var(--text-muted)' }}
              title="Close floating banner"
              aria-label="Close floating banner"
            >
              <span className="text-[10px]">Close</span>
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Banner Slots: Always Rendered on All Viewports */}
          <div className="w-full flex flex-wrap justify-center items-center gap-3 overflow-x-auto py-1">
            <div className="flex justify-center max-w-full overflow-x-auto">
              <AdBanner
                adKey={AD_CONFIG.leaderboard_728x90.key}
                width={AD_CONFIG.leaderboard_728x90.width}
                height={AD_CONFIG.leaderboard_728x90.height}
                label=""
                className="my-0"
                refreshInterval={25}
              />
            </div>

            <div className="flex justify-center max-w-full overflow-x-auto">
              <AdBanner
                adKey={AD_CONFIG.banner_468x60.key}
                width={AD_CONFIG.banner_468x60.width}
                height={AD_CONFIG.banner_468x60.height}
                label=""
                className="my-0"
                refreshInterval={25}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

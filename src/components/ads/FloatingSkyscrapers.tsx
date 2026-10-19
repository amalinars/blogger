'use client';

import React, { useState } from 'react';
import { X, Sparkles } from 'lucide-react';
import { AdBanner } from './AdBanner';
import { AD_CONFIG } from '@/lib/ad-config';

export function FloatingSkyscrapers() {
  const [showLeft, setShowLeft] = useState(true);
  const [showRight, setShowRight] = useState(true);

  return (
    <>
      {/* Partner L - Permanently Fixed on the Left Edge on ANY Resolution (Never Hidden) */}
      {showLeft && (
        <aside
          className="fixed top-20 sm:top-24 left-1 z-40 flex flex-col items-center animate-in fade-in slide-in-from-left-4 duration-500"
          aria-label="Sponsored Lateral Sidebar Left"
        >
          <div
            className="p-1 rounded-xl border shadow-2xl backdrop-blur-md relative"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.2)'
            }}
          >
            <div className="flex items-center justify-between w-full px-1.5 py-1 mb-1 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              <span className="text-[9px] font-mono uppercase tracking-wider opacity-70 font-semibold flex items-center space-x-1" style={{ color: 'var(--text-muted)' }}>
                <Sparkles className="w-2.5 h-2.5 text-amber-600 dark:text-amber-400" />
                <span>Partner L</span>
              </span>
              <button
                onClick={() => setShowLeft(false)}
                className="opacity-40 hover:opacity-100 transition-opacity p-0.5 cursor-pointer"
                title="Dismiss lateral banner"
                aria-label="Dismiss lateral banner"
              >
                <X className="w-3 h-3" />
              </button>
            </div>

            <AdBanner
              adKey={AD_CONFIG.skyscraper_160x600.key}
              width={AD_CONFIG.skyscraper_160x600.width}
              height={AD_CONFIG.skyscraper_160x600.height}
              label=""
              className="my-0"
              refreshInterval={25}
            />
          </div>
        </aside>
      )}

      {/* Partner R - Permanently Fixed on the Right Edge on ANY Resolution (Never Hidden) */}
      {showRight && (
        <aside
          className="fixed top-20 sm:top-24 right-1 z-40 flex flex-col items-center animate-in fade-in slide-in-from-right-4 duration-500"
          aria-label="Sponsored Lateral Sidebar Right"
        >
          <div
            className="p-1 rounded-xl border shadow-2xl backdrop-blur-md relative"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.2)'
            }}
          >
            <div className="flex items-center justify-between w-full px-1.5 py-1 mb-1 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              <span className="text-[9px] font-mono uppercase tracking-wider opacity-70 font-semibold flex items-center space-x-1" style={{ color: 'var(--text-muted)' }}>
                <Sparkles className="w-2.5 h-2.5 text-amber-600 dark:text-amber-400" />
                <span>Partner R</span>
              </span>
              <button
                onClick={() => setShowRight(false)}
                className="opacity-40 hover:opacity-100 transition-opacity p-0.5 cursor-pointer"
                title="Dismiss lateral banner"
                aria-label="Dismiss lateral banner"
              >
                <X className="w-3 h-3" />
              </button>
            </div>

            <AdBanner
              adKey={AD_CONFIG.skyscraper_160x600.key}
              width={AD_CONFIG.skyscraper_160x600.width}
              height={AD_CONFIG.skyscraper_160x600.height}
              label=""
              className="my-0"
              refreshInterval={25}
            />
          </div>
        </aside>
      )}
    </>
  );
}

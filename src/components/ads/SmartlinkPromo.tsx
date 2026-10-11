'use client';

import React from 'react';
import { ExternalLink, Sparkles } from 'lucide-react';

export function SmartlinkPromo() {
  const smartlinkUrl = 'https://araplhn.org/4/3714e867534d8e967cc514e3fe1e1f86';

  return (
    <aside
      className="p-5 rounded-xl border border-dashed my-6 relative overflow-hidden transition-all duration-300 hover:shadow-md"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        borderColor: 'var(--border-strong)'
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-widest text-amber-700 dark:text-amber-400 font-semibold flex items-center space-x-1">
          <Sparkles className="w-3 h-3" />
          <span>Curated Partner Dispatch</span>
        </span>
        <span className="text-[9px] font-mono opacity-50" style={{ color: 'var(--text-faint)' }}>
          Promoted
        </span>
      </div>

      <h4 className="font-serif text-sm font-bold leading-snug mb-1" style={{ color: 'var(--text-main)' }}>
        Discover Verified Tools, Cloud Infrastructure & Developer Insights
      </h4>
      <p className="text-xs font-sans leading-relaxed mb-3" style={{ color: 'var(--text-muted)' }}>
        Explore curated computational resources and ecosystem updates recommended for technical architects and digital artisans.
      </p>

      <a
        href={smartlinkUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium text-white transition-transform hover:scale-102 cursor-pointer shadow-xs"
        style={{ backgroundColor: 'var(--accent)' }}
      >
        <span>Explore Dispatch</span>
        <ExternalLink className="w-3 h-3" />
      </a>
    </aside>
  );
}

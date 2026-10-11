'use client';

import React, { useState } from 'react';
import { Share2, Check } from 'lucide-react';

export function ShareButton() {
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    try {
      if (typeof window !== 'undefined') {
        await navigator.clipboard.writeText(window.location.href);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      }
    } catch {
      // Fallback
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleShare}
        className="p-2.5 rounded-full border transition-all duration-200 cursor-pointer flex items-center justify-center hover:scale-105"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)',
          color: 'var(--text-main)'
        }}
        title="Copy article link"
      >
        {copied ? (
          <Check className="w-4 h-4 text-emerald-500" />
        ) : (
          <Share2 className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {copied && (
        <span
          className="absolute -top-8 left-1/2 -translate-x-1/2 px-2.5 py-1 rounded-md text-[10px] font-mono whitespace-nowrap shadow-md pointer-events-none animate-fadeIn"
          style={{
            backgroundColor: 'var(--text-main)',
            color: 'var(--bg-page)'
          }}
        >
          Link copied!
        </span>
      )}
    </div>
  );
}

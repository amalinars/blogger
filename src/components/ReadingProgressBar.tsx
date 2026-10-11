'use client';

import React, { useEffect, useState } from 'react';

export function ReadingProgressBar() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
      if (totalHeight > 0) {
        const currentProgress = (window.scrollY / totalHeight) * 100;
        setProgress(Math.min(100, Math.max(0, currentProgress)));
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="fixed top-0 left-0 w-full h-[3px] z-50 pointer-events-none bg-transparent">
      <div
        className="h-full transition-all duration-100 ease-out"
        style={{
          width: `${progress}%`,
          backgroundColor: 'var(--accent)',
          boxShadow: '0 0 10px var(--accent)'
        }}
      />
    </div>
  );
}

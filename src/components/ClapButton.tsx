'use client';

import React, { useState } from 'react';
import confetti from 'canvas-confetti';
import { Heart } from 'lucide-react';

interface ClapButtonProps {
  postId: string;
  initialClaps: number;
}

export function ClapButton({ postId, initialClaps }: ClapButtonProps) {
  const [claps, setClaps] = useState(initialClaps);
  const [isClapping, setIsClapping] = useState(false);

  const handleClap = async (e: React.MouseEvent<HTMLButtonElement>) => {
    // Confetti effect at button position
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (rect.left + rect.width / 2) / window.innerWidth;
    const y = (rect.top + rect.height / 2) / window.innerHeight;

    confetti({
      particleCount: 28,
      spread: 60,
      origin: { x, y },
      colors: ['#b45309', '#f59e0b', '#f97316', '#ef4444', '#fde68a']
    });

    // Optimistic state
    setClaps((prev) => prev + 1);
    setIsClapping(true);
    setTimeout(() => setIsClapping(false), 300);

    try {
      await fetch(`/api/posts/${postId}/clap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 1 })
      });
    } catch (err) {
      console.error('Failed to register clap:', err);
    }
  };

  return (
    <button
      onClick={handleClap}
      className={`px-4 py-2 rounded-full border transition-all duration-200 cursor-pointer flex items-center space-x-2 text-xs font-mono select-none ${
        isClapping ? 'scale-110 shadow-md' : 'hover:scale-105 hover:shadow-xs'
      }`}
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)',
        color: 'var(--text-main)'
      }}
      title="Applaud this dispatch"
    >
      <Heart
        className={`w-4 h-4 text-rose-500 transition-transform ${
          isClapping ? 'scale-125 fill-rose-500' : 'fill-rose-500/30'
        }`}
      />
      <span className="font-semibold">{claps}</span>
      <span className="text-[11px] opacity-70 hidden sm:inline">Claps</span>
    </button>
  );
}

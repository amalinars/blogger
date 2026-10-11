'use client';

import React from 'react';
import { useTheme } from './ThemeProvider';
import { Sun, Moon } from 'lucide-react';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
      className="p-2 rounded-full border transition-all duration-200 cursor-pointer flex items-center justify-center"
      style={{
        borderColor: 'var(--border-subtle)',
        backgroundColor: 'var(--bg-card)',
        color: 'var(--text-main)'
      }}
    >
      {theme === 'dark' ? (
        <Sun className="w-4 h-4 text-amber-400 hover:rotate-45 transition-transform duration-300" />
      ) : (
        <Moon className="w-4 h-4 text-amber-700 hover:-rotate-12 transition-transform duration-300" />
      )}
    </button>
  );
}

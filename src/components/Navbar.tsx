'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ThemeToggle } from './ThemeToggle';
import { PenTool, Search, BookOpen, Compass, Archive, Sparkles, X } from 'lucide-react';

export function Navbar() {
  const pathname = usePathname();
  const [currentDate, setCurrentDate] = useState('October 11, 2026');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const d = new Date();
    const formatted = d.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
    setCurrentDate(formatted);
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      window.location.href = `/?search=${encodeURIComponent(searchQuery.trim())}`;
    }
  };

  return (
    <header className="border-b transition-colors duration-200" style={{ borderColor: 'var(--border-subtle)' }}>
      {/* Editorial Top Ribbon */}
      <div
        className="text-xs border-b py-1.5 px-4 sm:px-8 flex justify-between items-center transition-colors duration-200 font-mono tracking-tight"
        style={{
          backgroundColor: 'var(--bg-subtle)',
          borderColor: 'var(--border-subtle)',
          color: 'var(--text-muted)'
        }}
      >
        <div className="flex items-center space-x-3">
          <span className="font-semibold text-amber-700 dark:text-amber-400">VOL. VII • ISSUE 42</span>
          <span className="hidden sm:inline opacity-40">|</span>
          <span className="hidden sm:inline">{currentDate}</span>
        </div>

        <div className="flex items-center space-x-4">
          <span className="hidden md:flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="text-[11px] opacity-80">Local-First Sovereign Edition</span>
          </span>
          <Link
            href="/studio"
            className="text-[11px] font-medium text-amber-700 dark:text-amber-400 hover:underline flex items-center space-x-1"
          >
            <span>Writer's Studio</span>
            <Sparkles className="w-3 h-3 inline" />
          </Link>
        </div>
      </div>

      {/* Main Masthead Banner */}
      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Brand Identity */}
        <div className="flex flex-col items-center sm:items-start text-center sm:text-left">
          <Link href="/" className="group inline-block">
            <h1
              className="font-serif text-3xl sm:text-5xl font-black tracking-tight tracking-wider transition-all duration-300"
              style={{ color: 'var(--text-main)' }}
            >
              C H R O N I C L E
            </h1>
          </Link>
          <p
            className="text-xs sm:text-sm tracking-widest uppercase mt-1 font-mono"
            style={{ color: 'var(--text-muted)' }}
          >
            The Monograph of Digital Craft & Computation
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setSearchOpen(!searchOpen)}
            className="p-2.5 rounded-full border transition-all duration-200 cursor-pointer flex items-center space-x-2 text-xs font-mono"
            style={{
              borderColor: 'var(--border-subtle)',
              backgroundColor: 'var(--bg-card)',
              color: 'var(--text-main)'
            }}
            title="Search essays"
          >
            <Search className="w-4 h-4 text-amber-700 dark:text-amber-400" />
            <span className="hidden md:inline pr-1">Search</span>
          </button>

          <Link
            href="/studio"
            className="px-4 py-2 rounded-full font-medium text-xs sm:text-sm transition-all duration-200 flex items-center space-x-2 shadow-xs cursor-pointer"
            style={{
              backgroundColor: 'var(--accent)',
              color: '#ffffff'
            }}
          >
            <PenTool className="w-3.5 h-3.5" />
            <span>Studio / New Post</span>
          </Link>

          <ThemeToggle />
        </div>
      </div>

      {/* Navigation Links Bar */}
      <nav
        className="border-t py-2.5 px-4 sm:px-8 transition-colors duration-200 overflow-x-auto"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <ul className="flex items-center space-x-1 sm:space-x-4 text-xs sm:text-sm font-medium">
            <li>
              <Link
                href="/"
                className={`px-3 py-1.5 rounded-md transition-colors ${
                  pathname === '/'
                    ? 'font-bold bg-amber-500/10 text-amber-700 dark:text-amber-400'
                    : 'hover:text-amber-600'
                }`}
                style={{ color: pathname === '/' ? undefined : 'var(--text-muted)' }}
              >
                Frontpage
              </Link>
            </li>
            <li>
              <Link
                href="/#topics"
                className="px-3 py-1.5 rounded-md transition-colors hover:text-amber-600"
                style={{ color: 'var(--text-muted)' }}
              >
                Topics & Taxonomy
              </Link>
            </li>
            <li>
              <Link
                href="/archive"
                className={`px-3 py-1.5 rounded-md transition-colors flex items-center space-x-1 ${
                  pathname === '/archive'
                    ? 'font-bold bg-amber-500/10 text-amber-700 dark:text-amber-400'
                    : 'hover:text-amber-600'
                }`}
                style={{ color: pathname === '/archive' ? undefined : 'var(--text-muted)' }}
              >
                <Archive className="w-3.5 h-3.5 inline mr-1" />
                <span>Archive Timeline</span>
              </Link>
            </li>
            <li>
              <Link
                href="/studio"
                className={`px-3 py-1.5 rounded-md transition-colors flex items-center space-x-1 ${
                  pathname === '/studio'
                    ? 'font-bold bg-amber-500/10 text-amber-700 dark:text-amber-400'
                    : 'hover:text-amber-600'
                }`}
                style={{ color: pathname === '/studio' ? undefined : 'var(--text-muted)' }}
              >
                <span>Editorial Desk</span>
              </Link>
            </li>
          </ul>

          <div className="hidden lg:flex items-center text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
            <span>ISSN 2940-184X</span>
          </div>
        </div>
      </nav>

      {/* Expandable Search Drawer */}
      {searchOpen && (
        <div
          className="border-t py-4 px-4 sm:px-8 transition-all animate-fadeIn"
          style={{
            backgroundColor: 'var(--bg-card)',
            borderColor: 'var(--border-subtle)'
          }}
        >
          <form onSubmit={handleSearchSubmit} className="max-w-3xl mx-auto flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search across all essays, authors, and philosophies..."
                className="w-full pl-10 pr-4 py-2 text-sm rounded-lg border outline-none font-sans"
                style={{
                  borderColor: 'var(--border-subtle)',
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-main)'
                }}
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium rounded-lg text-white font-mono cursor-pointer"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              Search
            </button>
            <button
              type="button"
              onClick={() => setSearchOpen(false)}
              className="p-2 rounded-lg border cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-muted)' }}
            >
              <X className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </header>
  );
}

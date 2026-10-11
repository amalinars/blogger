'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Send, CheckCircle2 } from 'lucide-react';

export function Footer() {
  const [email, setEmail] = useState('');
  const [subscribed, setSubscribed] = useState(false);

  const handleSubscribe = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim()) {
      setSubscribed(true);
    }
  };

  return (
    <footer
      className="border-t mt-20 transition-colors duration-200"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)'
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-12">
          {/* Column 1: Manifesto */}
          <div className="md:col-span-5 space-y-4">
            <h3
              className="font-serif text-2xl font-bold tracking-tight"
              style={{ color: 'var(--text-main)' }}
            >
              C H R O N I C L E
            </h3>
            <p
              className="text-sm leading-relaxed max-w-md font-sans"
              style={{ color: 'var(--text-muted)' }}
            >
              An independent digital journal dedicated to reclaiming intentionality in software,
              investigating typographic rhythm, distributed systems resilience, and the tactile poetics of computing.
            </p>
            <div className="pt-2 font-mono text-xs" style={{ color: 'var(--text-faint)' }}>
              <span>Typography: Newsreader Display & JetBrains Mono</span>
              <br />
              <span>Full-Stack Next.js Sovereign Architecture</span>
            </div>
          </div>

          {/* Column 2: Sections */}
          <div className="md:col-span-3 space-y-3">
            <h4 className="text-xs font-mono uppercase tracking-wider font-semibold" style={{ color: 'var(--text-main)' }}>
              Topical Taxonomy
            </h4>
            <ul className="space-y-2 text-sm" style={{ color: 'var(--text-muted)' }}>
              <li>
                <Link href="/?category=Design+%26+Craft" className="hover:text-amber-600 transition-colors">
                  Design & Craft
                </Link>
              </li>
              <li>
                <Link href="/?category=Technology" className="hover:text-amber-600 transition-colors">
                  Systems & Technology
                </Link>
              </li>
              <li>
                <Link href="/?category=Artificial+Intelligence" className="hover:text-amber-600 transition-colors">
                  Artificial Intelligence
                </Link>
              </li>
              <li>
                <Link href="/?category=Culture+%26+Web" className="hover:text-amber-600 transition-colors">
                  Culture & Personal Web
                </Link>
              </li>
              <li>
                <Link href="/archive" className="hover:text-amber-600 transition-colors">
                  Complete Chronological Archive
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3: The Monograph Dispatch (Newsletter) */}
          <div className="md:col-span-4 space-y-4">
            <h4 className="text-xs font-mono uppercase tracking-wider font-semibold" style={{ color: 'var(--text-main)' }}>
              The Bi-Weekly Dispatch
            </h4>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Receive long-form essays, typographic specimens, and systems architecture essays delivered directly to your inbox. No spam, ever.
            </p>

            {subscribed ? (
              <div
                className="p-3 rounded-lg border flex items-center space-x-2 text-xs font-mono text-emerald-600 dark:text-emerald-400"
                style={{
                  backgroundColor: 'var(--bg-subtle)',
                  borderColor: 'var(--border-subtle)'
                }}
              >
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                <span>You are subscribed to the Chronicle Dispatch.</span>
              </div>
            ) : (
              <form onSubmit={handleSubscribe} className="flex gap-2">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="editor@monograph.org"
                  className="flex-1 px-3 py-2 text-xs rounded-lg border outline-none font-mono"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    backgroundColor: 'var(--bg-subtle)',
                    color: 'var(--text-main)'
                  }}
                />
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg text-xs font-medium text-white flex items-center space-x-1 cursor-pointer transition-opacity hover:opacity-90 font-mono"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  <span>Join</span>
                  <Send className="w-3 h-3" />
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Colophon bottom bar */}
        <div
          className="border-t mt-12 pt-8 flex flex-col sm:flex-row justify-between items-center text-xs font-mono gap-4"
          style={{
            borderColor: 'var(--border-subtle)',
            color: 'var(--text-faint)'
          }}
        >
          <div>
            © 2026 CHRONICLE JOURNAL. Published with Next.js Full-Stack App Router.
          </div>
          <div className="flex items-center space-x-6">
            <Link href="/studio" className="hover:text-amber-600 underline">
              Publishing Studio
            </Link>
            <Link href="/archive" className="hover:text-amber-600 underline">
              Archives
            </Link>
            <span>Handcrafted without generic templates</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

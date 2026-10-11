'use client';

import React from 'react';
import Link from 'next/link';
import { Post, ArchiveItem } from '@/lib/types';
import { Tag, TrendingUp, Calendar, Feather, ArrowUpRight } from 'lucide-react';
import { AdBanner, AD_CONFIG } from './ads/AdBanner';
import { SmartlinkPromo } from './ads/SmartlinkPromo';

interface SidebarProps {
  trendingPosts: Post[];
  tags: { tag: string; count: number }[];
  archives: ArchiveItem[];
  onSelectTag?: (tag: string) => void;
  selectedTag?: string;
}

export function Sidebar({
  trendingPosts,
  tags,
  archives,
  onSelectTag,
  selectedTag
}: SidebarProps) {
  return (
    <aside className="space-y-8">
      {/* Widget 1: About the Publication */}
      <div
        className="p-6 rounded-xl border space-y-4"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex items-center space-x-2 text-xs font-mono font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
          <Feather className="w-4 h-4" />
          <span>About The Publication</span>
        </div>
        <p className="text-xs sm:text-sm leading-relaxed font-sans" style={{ color: 'var(--text-muted)' }}>
          Chronicle publishes long-form inquiries into the craft of digital tools, typographic poise,
          and resilient distributed architecture. We reject algorithmic churn in pursuit of durable ideas.
        </p>
        <div
          className="pt-3 border-t flex items-center justify-between text-xs font-mono"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <span style={{ color: 'var(--text-faint)' }}>Founded: Autumn 2026</span>
          <Link href="/studio" className="text-amber-700 dark:text-amber-400 hover:underline flex items-center">
            <span>Open Studio</span>
            <ArrowUpRight className="w-3 h-3 ml-0.5 inline" />
          </Link>
        </div>
      </div>

      {/* Widget 2: Trending Dispatches */}
      <div
        className="p-6 rounded-xl border space-y-4"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex items-center space-x-2 text-xs font-mono font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
          <TrendingUp className="w-4 h-4" />
          <span>Trending Dispatches</span>
        </div>

        <div className="space-y-3.5">
          {trendingPosts.slice(0, 4).map((post, index) => (
            <Link
              key={post.id}
              href={`/post/${post.slug}`}
              className="group flex items-start space-x-3 transition-colors"
            >
              <span
                className="font-serif text-lg font-bold leading-none select-none transition-colors group-hover:text-amber-600"
                style={{ color: 'var(--text-faint)' }}
              >
                0{index + 1}
              </span>
              <div className="space-y-1">
                <h4
                  className="text-xs sm:text-sm font-serif font-bold leading-snug group-hover:text-amber-600 transition-colors line-clamp-2"
                  style={{ color: 'var(--text-main)' }}
                >
                  {post.title}
                </h4>
                <div className="flex items-center space-x-2 text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  <span>{post.readTimeMinutes}m read</span>
                  <span>•</span>
                  <span>{post.claps} claps</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Adsterra 300x250 Rectangle Ad Slot */}
      <div
        className="p-4 rounded-xl border flex flex-col items-center justify-center overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <AdBanner
          adKey={AD_CONFIG.rectangle_300x250.key}
          width={AD_CONFIG.rectangle_300x250.width}
          height={AD_CONFIG.rectangle_300x250.height}
          label="Partner Dispatch"
        />
      </div>

      {/* Widget 3: Taxonomy & Tag Cloud */}
      <div
        className="p-6 rounded-xl border space-y-4"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex items-center space-x-2 text-xs font-mono font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
          <Tag className="w-4 h-4" />
          <span>Taxonomy Cloud</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {tags.map(({ tag, count }) => {
            const isSelected = selectedTag?.toLowerCase() === tag.toLowerCase();
            return (
              <button
                key={tag}
                onClick={() => onSelectTag && onSelectTag(isSelected ? '' : tag)}
                className={`px-2.5 py-1 rounded-md text-xs font-mono transition-all cursor-pointer flex items-center space-x-1 ${
                  isSelected
                    ? 'bg-amber-600 text-white font-semibold'
                    : 'border hover:border-amber-500'
                }`}
                style={{
                  backgroundColor: isSelected ? 'var(--accent)' : 'var(--bg-subtle)',
                  borderColor: isSelected ? 'transparent' : 'var(--border-subtle)',
                  color: isSelected ? '#ffffff' : 'var(--text-main)'
                }}
              >
                <span>#{tag}</span>
                <span className="opacity-60 text-[10px]">({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Widget 4: Chronological Archive */}
      <div
        className="p-6 rounded-xl border space-y-4"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex items-center space-x-2 text-xs font-mono font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
          <Calendar className="w-4 h-4" />
          <span>Chronological Archive</span>
        </div>

        <ul className="space-y-2 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          {archives.map((item) => (
            <li key={`${item.year}-${item.month}`}>
              <Link
                href="/archive"
                className="flex items-center justify-between hover:text-amber-600 transition-colors py-1 border-b border-dashed"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <span>{item.month} {item.year}</span>
                <span
                  className="px-1.5 py-0.5 rounded text-[10px]"
                  style={{ backgroundColor: 'var(--bg-subtle)', color: 'var(--text-faint)' }}
                >
                  {item.count} {item.count === 1 ? 'dispatch' : 'dispatches'}
                </span>
              </Link>
            </li>
          ))}
        </ul>

        <div className="pt-2 text-center">
          <Link
            href="/archive"
            className="text-xs font-mono text-amber-700 dark:text-amber-400 hover:underline"
          >
            Explore Full Timeline →
          </Link>
        </div>
      </div>

      {/* Smartlink Partner Recommendation */}
      <SmartlinkPromo />
    </aside>
  );
}

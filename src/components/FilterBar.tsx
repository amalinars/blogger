'use client';

import React from 'react';
import { LayoutGrid, List, Sparkles, Flame, Eye, Search, X } from 'lucide-react';

interface FilterBarProps {
  categories: string[];
  activeCategory: string;
  onSelectCategory: (category: string) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortMode: 'latest' | 'claps' | 'views';
  onSortChange: (sort: 'latest' | 'claps' | 'views') => void;
  viewMode: 'grid' | 'list';
  onViewModeChange: (mode: 'grid' | 'list') => void;
  totalCount: number;
}

export function FilterBar({
  categories,
  activeCategory,
  onSelectCategory,
  searchQuery,
  onSearchChange,
  sortMode,
  onSortChange,
  viewMode,
  onViewModeChange,
  totalCount
}: FilterBarProps) {
  return (
    <div className="space-y-4 my-8">
      {/* Category Tabs & View Switcher */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Horizontal Category Pills */}
        <div className="flex items-center space-x-1.5 overflow-x-auto pb-2 md:pb-0 scrollbar-none">
          <button
            onClick={() => onSelectCategory('all')}
            className={`px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider transition-all duration-200 cursor-pointer whitespace-nowrap ${
              activeCategory === 'all'
                ? 'bg-amber-600 text-white font-bold shadow-xs'
                : 'border hover:border-amber-500'
            }`}
            style={{
              backgroundColor: activeCategory === 'all' ? 'var(--accent)' : 'var(--bg-card)',
              borderColor: activeCategory === 'all' ? 'transparent' : 'var(--border-subtle)',
              color: activeCategory === 'all' ? '#ffffff' : 'var(--text-main)'
            }}
          >
            All Dispatches ({totalCount})
          </button>

          {categories.map((cat) => {
            const isSelected = activeCategory.toLowerCase() === cat.toLowerCase();
            return (
              <button
                key={cat}
                onClick={() => onSelectCategory(cat)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-mono tracking-wide transition-all duration-200 cursor-pointer whitespace-nowrap ${
                  isSelected
                    ? 'bg-amber-600 text-white font-bold shadow-xs'
                    : 'border hover:border-amber-500'
                }`}
                style={{
                  backgroundColor: isSelected ? 'var(--accent)' : 'var(--bg-card)',
                  borderColor: isSelected ? 'transparent' : 'var(--border-subtle)',
                  color: isSelected ? '#ffffff' : 'var(--text-main)'
                }}
              >
                {cat}
              </button>
            );
          })}
        </div>

        {/* View Mode & Sorter */}
        <div className="flex items-center space-x-2 self-end md:self-auto">
          {/* Sort Selector */}
          <div
            className="flex items-center border rounded-lg p-0.5 text-xs font-mono"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <button
              onClick={() => onSortChange('latest')}
              title="Sort by latest"
              className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer flex items-center space-x-1 ${
                sortMode === 'latest' ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400 font-semibold' : 'text-gray-500'
              }`}
            >
              <Sparkles className="w-3 h-3" />
              <span className="hidden sm:inline">Latest</span>
            </button>

            <button
              onClick={() => onSortChange('claps')}
              title="Sort by most clapped"
              className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer flex items-center space-x-1 ${
                sortMode === 'claps' ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400 font-semibold' : 'text-gray-500'
              }`}
            >
              <Flame className="w-3 h-3 text-rose-500" />
              <span className="hidden sm:inline">Top Claps</span>
            </button>

            <button
              onClick={() => onSortChange('views')}
              title="Sort by most views"
              className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer flex items-center space-x-1 ${
                sortMode === 'views' ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400 font-semibold' : 'text-gray-500'
              }`}
            >
              <Eye className="w-3 h-3 text-blue-500" />
              <span className="hidden sm:inline">Views</span>
            </button>
          </div>

          {/* Grid vs Feed List Toggle */}
          <div
            className="flex items-center border rounded-lg p-0.5"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <button
              onClick={() => onViewModeChange('grid')}
              className={`p-1.5 rounded-md cursor-pointer ${
                viewMode === 'grid' ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400' : 'text-gray-400'
              }`}
              title="Grid View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onViewModeChange('list')}
              className={`p-1.5 rounded-md cursor-pointer ${
                viewMode === 'list' ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400' : 'text-gray-400'
              }`}
              title="Feed List View"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Live Search bar */}
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter stories by keywords (e.g. latency, craft, typography, local-first)..."
          className="w-full pl-10 pr-10 py-2.5 text-xs sm:text-sm rounded-xl border outline-none font-sans transition-all focus:ring-1 focus:ring-amber-500"
          style={{
            borderColor: 'var(--border-subtle)',
            backgroundColor: 'var(--bg-card)',
            color: 'var(--text-main)'
          }}
        />
        {searchQuery && (
          <button
            onClick={() => onSearchChange('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}

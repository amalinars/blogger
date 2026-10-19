'use client';

import React, { useState, useMemo } from 'react';
import { Post, ArchiveItem, Category } from '@/lib/types';
import { HeroPost } from './HeroPost';
import { PostCard } from './PostCard';
import { FilterBar } from './FilterBar';
import { Sidebar } from './Sidebar';
import { BookOpen } from 'lucide-react';
import { AdBanner, AD_CONFIG } from './ads/AdBanner';
import { NativeBanner } from './ads/NativeBanner';

interface HomeFeedProps {
  initialPosts: Post[];
  categories: Category[];
  tags: { tag: string; count: number }[];
  archives: ArchiveItem[];
}

export function HomeFeed({
  initialPosts,
  categories,
  tags,
  archives
}: HomeFeedProps) {
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [selectedTag, setSelectedTag] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortMode, setSortMode] = useState<'latest' | 'claps' | 'views'>('latest');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  // Featured post is the first featured or latest post
  const featuredPost = useMemo(() => {
    return initialPosts.find((p) => p.isFeatured) || initialPosts[0];
  }, [initialPosts]);

  // Filter & sort remaining posts
  const filteredPosts = useMemo(() => {
    let list = [...initialPosts];

    // If on "all" and no search/tag filter, exclude featuredPost from the main grid so it's not duplicated
    const isFiltered = activeCategory !== 'all' || selectedTag || searchQuery.trim().length > 0;
    if (!isFiltered && featuredPost) {
      list = list.filter((p) => p.id !== featuredPost.id);
    }

    if (activeCategory !== 'all') {
      list = list.filter(
        (p) => p.category.toLowerCase() === activeCategory.toLowerCase()
      );
    }

    if (selectedTag) {
      list = list.filter((p) =>
        p.tags.some((t) => t.toLowerCase() === selectedTag.toLowerCase())
      );
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.excerpt.toLowerCase().includes(q) ||
          p.content.toLowerCase().includes(q) ||
          p.author.name.toLowerCase().includes(q) ||
          p.tags.some((t) => t.toLowerCase().includes(q))
      );
    }

    if (sortMode === 'claps') {
      list.sort((a, b) => b.claps - a.claps);
    } else if (sortMode === 'views') {
      list.sort((a, b) => b.views - a.views);
    } else {
      list.sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      );
    }

    return list;
  }, [initialPosts, activeCategory, selectedTag, searchQuery, sortMode, featuredPost]);

  const categoryNames = useMemo(() => {
    return categories.map((c) => c.name);
  }, [categories]);

  return (
    <div className="space-y-12">
      {/* Lead Hero Dispatch */}
      {featuredPost && activeCategory === 'all' && !searchQuery && !selectedTag && (
        <section aria-label="Lead Story">
          <HeroPost post={featuredPost} />
        </section>
      )}

      {/* Editorial Leaderboard Banner */}
      <div className="w-full flex justify-center items-center py-2">
        <div className="flex justify-center max-w-full overflow-x-auto">
          <AdBanner
            adKey={AD_CONFIG.leaderboard_728x90.key}
            width={AD_CONFIG.leaderboard_728x90.width}
            height={AD_CONFIG.leaderboard_728x90.height}
            label="Sponsored Dispatch"
            autoRefresh={false}
          />
        </div>
      </div>

      {/* Main Grid & Classic Blogspot Sidebar Section */}
      <section id="topics" className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* Main Feed Column */}
        <div className="lg:col-span-8">
          {/* Controls */}
          <FilterBar
            categories={categoryNames}
            activeCategory={activeCategory}
            onSelectCategory={(cat) => {
              setActiveCategory(cat);
              setSelectedTag('');
            }}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            sortMode={sortMode}
            onSortChange={setSortMode}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            totalCount={filteredPosts.length + (featuredPost && activeCategory === 'all' && !searchQuery && !selectedTag ? 1 : 0)}
          />

          {/* Active Tag Filter Pill */}
          {selectedTag && (
            <div
              className="mb-6 p-3 rounded-lg border flex items-center justify-between text-xs font-mono"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span>
                Filtered by tag: <strong className="text-amber-700 dark:text-amber-400">#{selectedTag}</strong>
              </span>
              <button
                onClick={() => setSelectedTag('')}
                className="underline hover:text-amber-600 cursor-pointer"
              >
                Clear tag filter
              </button>
            </div>
          )}

          {/* Posts Feed */}
          {filteredPosts.length === 0 ? (
            <div
              className="text-center py-20 px-6 rounded-2xl border"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <BookOpen className="w-12 h-12 mx-auto mb-3 opacity-30 text-amber-600" />
              <h3 className="font-serif text-xl font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                No dispatches found
              </h3>
              <p className="text-xs sm:text-sm font-sans mb-4" style={{ color: 'var(--text-muted)' }}>
                Try adjusting your search terms or clearing topical filters.
              </p>
              <button
                onClick={() => {
                  setActiveCategory('all');
                  setSelectedTag('');
                  setSearchQuery('');
                }}
                className="px-4 py-2 rounded-lg text-xs font-mono font-medium text-white cursor-pointer"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                Reset All Filters
              </button>
            </div>
          ) : viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {filteredPosts.map((post, index) => (
                <React.Fragment key={post.id}>
                  <PostCard post={post} viewMode="grid" />
                  {(index + 1) % 6 === 0 && index < filteredPosts.length - 1 && (
                    <div className="md:col-span-2 w-full flex justify-center items-center py-2">
                      <div className="flex justify-center max-w-full overflow-x-auto">
                        <AdBanner
                          adKey={AD_CONFIG.leaderboard_728x90.key}
                          width={AD_CONFIG.leaderboard_728x90.width}
                          height={AD_CONFIG.leaderboard_728x90.height}
                          label="Featured Dispatch"
                          autoRefresh={false}
                        />
                      </div>
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredPosts.map((post, index) => (
                <React.Fragment key={post.id}>
                  <PostCard post={post} viewMode="list" />
                  {(index + 1) % 5 === 0 && index < filteredPosts.length - 1 && (
                    <div className="w-full flex justify-center items-center py-2">
                      <div className="flex justify-center max-w-full overflow-x-auto">
                        <AdBanner
                          adKey={AD_CONFIG.leaderboard_728x90.key}
                          width={AD_CONFIG.leaderboard_728x90.width}
                          height={AD_CONFIG.leaderboard_728x90.height}
                          label="Featured Dispatch"
                          autoRefresh={false}
                        />
                      </div>
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          {/* Adsterra Native Banner Recommendations */}
          <NativeBanner />
        </div>

        {/* Sidebar Column */}
        <div className="lg:col-span-4">
          <Sidebar
            trendingPosts={initialPosts}
            tags={tags}
            archives={archives}
            selectedTag={selectedTag}
            onSelectTag={(tag) => {
              setSelectedTag(tag);
              setActiveCategory('all');
            }}
          />
        </div>
      </section>
    </div>
  );
}

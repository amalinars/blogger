import React from 'react';
import Link from 'next/link';
import { Post } from '@/lib/types';
import { Clock, Heart, Eye, ArrowRight } from 'lucide-react';

interface PostCardProps {
  post: Post;
  viewMode?: 'grid' | 'list';
}

export function PostCard({ post, viewMode = 'grid' }: PostCardProps) {
  const formattedDate = new Date(post.createdAt).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });

  if (viewMode === 'list') {
    return (
      <article
        className="group p-6 rounded-xl border transition-all duration-200 hover:shadow-md flex flex-col sm:flex-row gap-6 items-start sm:items-center justify-between"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex-1 space-y-2">
          <div className="flex items-center space-x-2 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            <span className="font-semibold text-amber-700 dark:text-amber-400 uppercase">
              {post.category}
            </span>
            <span>•</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold border border-emerald-500/20">
              4-Layer Gateway
            </span>
            <span>•</span>
            <span>{post.readTimeMinutes}m read</span>
          </div>

          <Link href={`/post/${post.slug}?step=1`} className="block group-hover:text-amber-600 transition-colors">
            <h3
              className="font-serif text-xl sm:text-2xl font-bold leading-snug tracking-tight"
              style={{ color: 'var(--text-main)' }}
            >
              {post.title}
            </h3>
          </Link>

          <p
            className="text-xs sm:text-sm line-clamp-2 leading-relaxed font-sans"
            style={{ color: 'var(--text-muted)' }}
          >
            {post.excerpt}
          </p>

          <div className="flex items-center space-x-4 pt-2 text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
            <span className="font-sans font-medium" style={{ color: 'var(--text-main)' }}>
              By {post.author.name}
            </span>
            <span className="flex items-center space-x-1">
              <Heart className="w-3 h-3 text-rose-500" />
              <span>{post.claps}</span>
            </span>
            <span className="flex items-center space-x-1">
              <Eye className="w-3 h-3" />
              <span>{post.views}</span>
            </span>
          </div>
        </div>

        {post.coverImage && (
          <div className="w-full sm:w-44 h-32 flex-shrink-0 rounded-lg overflow-hidden border" style={{ borderColor: 'var(--border-subtle)' }}>
            <img
              src={post.coverImage}
              alt={post.title}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            />
          </div>
        )}
      </article>
    );
  }

  return (
    <article
      className="group rounded-xl border overflow-hidden flex flex-col justify-between transition-all duration-300 hover:shadow-lg"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)'
      }}
    >
      <div>
        {/* Card Image */}
        <div className="relative h-48 overflow-hidden">
          <img
            src={post.coverImage}
            alt={post.title}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
          <div className="absolute top-3 left-3">
            <span
              className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium tracking-wide uppercase shadow-xs"
              style={{
                backgroundColor: 'var(--bg-card)',
                color: 'var(--text-main)',
                border: '1px solid var(--border-subtle)'
              }}
            >
              {post.category}
            </span>
          </div>
        </div>

        {/* Card Content */}
        <div className="p-5 space-y-3">
          <div className="flex items-center space-x-2 text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold border border-emerald-500/20">
              Stage 1/4
            </span>
            <span>•</span>
            <span className="flex items-center">
              <Clock className="w-2.5 h-2.5 mr-1 inline" />
              {post.readTimeMinutes} min
            </span>
          </div>

          <Link href={`/post/${post.slug}?step=1`} className="block group-hover:text-amber-700 dark:group-hover:text-amber-400 transition-colors">
            <h3
              className="font-serif text-lg sm:text-xl font-bold leading-snug tracking-tight line-clamp-2"
              style={{ color: 'var(--text-main)' }}
            >
              {post.title}
            </h3>
          </Link>

          <p
            className="text-xs sm:text-sm line-clamp-3 leading-relaxed font-sans"
            style={{ color: 'var(--text-muted)' }}
          >
            {post.excerpt}
          </p>
        </div>
      </div>

      {/* Card Footer */}
      <div
        className="px-5 py-4 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center space-x-2.5">
          <img
            src={post.author.avatar}
            alt={post.author.name}
            className="w-6 h-6 rounded-full object-cover border"
            style={{ borderColor: 'var(--border-subtle)' }}
          />
          <span className="text-xs font-medium" style={{ color: 'var(--text-main)' }}>
            {post.author.name}
          </span>
        </div>

        <div className="flex items-center space-x-3 text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
          <span className="flex items-center space-x-1">
            <Heart className="w-3 h-3 text-rose-500/80" />
            <span>{post.claps}</span>
          </span>

          <Link
            href={`/post/${post.slug}?step=1`}
            className="text-amber-700 dark:text-amber-400 hover:underline flex items-center font-semibold text-[11px]"
            title="Start Step 1 Gateway"
          >
            <span>Start</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </Link>
        </div>
      </div>
    </article>
  );
}

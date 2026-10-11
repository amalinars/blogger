import React from 'react';
import Link from 'next/link';
import { Post } from '@/lib/types';
import { Clock, Heart, MessageSquare, ArrowUpRight } from 'lucide-react';

export function HeroPost({ post }: { post: Post }) {
  const formattedDate = new Date(post.createdAt).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  return (
    <article
      className="relative rounded-2xl border overflow-hidden transition-all duration-300 group hover:shadow-xl"
      style={{
        backgroundColor: 'var(--bg-card)',
        borderColor: 'var(--border-subtle)'
      }}
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-0">
        {/* Cover Image Half */}
        <div className="lg:col-span-7 relative h-72 sm:h-96 lg:h-full min-h-[340px] overflow-hidden">
          <img
            src={post.coverImage}
            alt={post.title}
            className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent lg:hidden" />
          <div className="absolute top-4 left-4 z-10">
            <span
              className="px-3 py-1 rounded-full text-xs font-mono font-semibold tracking-wide uppercase shadow-sm"
              style={{
                backgroundColor: 'var(--accent)',
                color: '#ffffff'
              }}
            >
              Featured Dispatch
            </span>
          </div>
        </div>

        {/* Content Half */}
        <div className="lg:col-span-5 p-6 sm:p-10 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center space-x-3 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              <span className="font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wider">
                {post.category}
              </span>
              <span>•</span>
              <span>{formattedDate}</span>
              <span>•</span>
              <span className="flex items-center">
                <Clock className="w-3 h-3 mr-1 inline" />
                {post.readTimeMinutes} min read
              </span>
            </div>

            <Link href={`/post/${post.slug}`} className="block group-hover:text-amber-700 dark:group-hover:text-amber-400 transition-colors">
              <h2
                className="font-serif text-2xl sm:text-3xl lg:text-4xl font-bold leading-tight tracking-tight"
                style={{ color: 'var(--text-main)' }}
              >
                {post.title}
              </h2>
            </Link>

            <p
              className="text-sm sm:text-base leading-relaxed line-clamp-3 font-sans"
              style={{ color: 'var(--text-muted)' }}
            >
              {post.excerpt}
            </p>
          </div>

          <div
            className="pt-6 mt-6 border-t flex items-center justify-between"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            {/* Author */}
            <div className="flex items-center space-x-3">
              <img
                src={post.author.avatar}
                alt={post.author.name}
                className="w-10 h-10 rounded-full object-cover border"
                style={{ borderColor: 'var(--border-subtle)' }}
              />
              <div>
                <h4 className="text-xs font-semibold leading-tight" style={{ color: 'var(--text-main)' }}>
                  {post.author.name}
                </h4>
                <p className="text-[11px] font-mono leading-tight" style={{ color: 'var(--text-muted)' }}>
                  {post.author.role}
                </p>
              </div>
            </div>

            {/* Read Link & Claps */}
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-1 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                <Heart className="w-3.5 h-3.5 text-rose-500 fill-rose-500/20" />
                <span>{post.claps}</span>
              </div>

              <Link
                href={`/post/${post.slug}`}
                className="p-2 rounded-full border transition-all duration-200 group-hover:bg-amber-600 group-hover:text-white group-hover:border-transparent flex items-center justify-center cursor-pointer"
                style={{
                  borderColor: 'var(--border-subtle)',
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-main)'
                }}
                title="Read essay"
              >
                <ArrowUpRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

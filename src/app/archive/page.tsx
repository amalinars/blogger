import React from 'react';
import Link from 'next/link';
import { getArchive, getAllPosts } from '@/lib/db';
import { Calendar, ArrowRight, ArrowLeft, BookOpen, Clock } from 'lucide-react';


export const metadata = {
  title: 'Chronological Archive — Chronicle',
  description: 'The complete timeline index of all published dispatches and essays in Chronicle.'
};

export default async function ArchivePage() {
  const archives = getArchive();
  const allPosts = getAllPosts({ status: 'published' });

  return (
    <div className="animate-fadeIn max-w-4xl mx-auto space-y-12 pb-16">
      {/* Header */}
      <div className="space-y-4">
        <Link
          href="/"
          className="inline-flex items-center space-x-1.5 text-xs font-mono hover:text-amber-600 transition-colors"
          style={{ color: 'var(--text-muted)' }}
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Return to Journal</span>
        </Link>

        <div className="space-y-2">
          <span className="text-xs font-mono uppercase tracking-widest text-amber-700 dark:text-amber-400 font-semibold">
            Historical Registry
          </span>
          <h1 className="font-serif text-3xl sm:text-5xl font-bold tracking-tight" style={{ color: 'var(--text-main)' }}>
            The Chronicle Archive
          </h1>
          <p className="text-sm sm:text-base font-sans" style={{ color: 'var(--text-muted)' }}>
            Every long-form inquiry, architectural analysis, and typographic essay preserved in chronological order.
          </p>
        </div>
      </div>

      {/* Timeline Sections */}
      <div className="space-y-10">
        {archives.map((item) => (
          <div
            key={`${item.year}-${item.month}`}
            className="p-6 sm:p-8 rounded-2xl border space-y-6"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <div className="flex items-center justify-between border-b pb-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center space-x-2">
                <Calendar className="w-4 h-4 text-amber-600" />
                <h2 className="font-serif text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
                  {item.month} {item.year}
                </h2>
              </div>
              <span className="text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
                {item.count} {item.count === 1 ? 'dispatch' : 'dispatches'}
              </span>
            </div>

            <div className="space-y-4">
              {item.posts.map((post) => {
                const dateStr = new Date(post.createdAt).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric'
                });

                return (
                  <Link
                    key={post.id}
                    href={`/post/${post.slug}`}
                    className="group flex flex-col sm:flex-row sm:items-center justify-between py-2 border-b border-dashed transition-colors"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div className="flex items-center space-x-3">
                      <span className="text-xs font-mono w-14 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
                        {dateStr}
                      </span>
                      <h3
                        className="font-serif text-base font-semibold group-hover:text-amber-600 transition-colors"
                        style={{ color: 'var(--text-main)' }}
                      >
                        {post.title}
                      </h3>
                    </div>

                    <div className="flex items-center space-x-3 mt-1 sm:mt-0 text-xs font-mono self-end sm:self-auto" style={{ color: 'var(--text-faint)' }}>
                      <span className="uppercase text-[10px] px-2 py-0.5 rounded border" style={{ borderColor: 'var(--border-subtle)' }}>
                        {post.category}
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

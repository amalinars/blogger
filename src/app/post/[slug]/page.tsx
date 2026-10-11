import React from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { marked } from 'marked';
import {
  getPostBySlug,
  incrementViews,
  getComments,
  getAllPosts
} from '@/lib/db';
import { ReadingProgressBar } from '@/components/ReadingProgressBar';
import { ClapButton } from '@/components/ClapButton';
import { BookmarkButton } from '@/components/BookmarkButton';
import { ShareButton } from '@/components/ShareButton';
import { TableOfContents } from '@/components/TableOfContents';
import { CommentsSection } from '@/components/CommentsSection';
import { Clock, Calendar, ArrowLeft, Heart, Eye, ArrowUpRight } from 'lucide-react';
import { AdBanner } from '@/components/ads/AdBanner';
import { AD_CONFIG } from '@/lib/ad-config';
import { NativeBanner } from '@/components/ads/NativeBanner';
import { SmartlinkPromo } from '@/components/ads/SmartlinkPromo';


export async function generateMetadata({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = getPostBySlug(slug);
  if (!post) return { title: 'Post Not Found — Chronicle' };

  return {
    title: `${post.title} — Chronicle`,
    description: post.excerpt
  };
}

export default async function PostPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = getPostBySlug(slug);

  if (!post) {
    notFound();
  }

  // Increment view count
  incrementViews(post.slug);
  const comments = getComments(post.id);

  // Convert markdown to HTML
  const contentHtml = await marked.parse(post.content);

  // Recommended related posts
  const allPosts = getAllPosts({ status: 'published' });
  const relatedPosts = allPosts
    .filter((p) => p.id !== post.id && (p.category === post.category || p.tags.some((t) => post.tags.includes(t))))
    .slice(0, 3);

  const formattedDate = new Date(post.createdAt).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });

  return (
    <article className="animate-fadeIn pb-16">
      <ReadingProgressBar />

      {/* Back button & topical breadcrumb */}
      <div className="mb-8 flex items-center justify-between text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
        <Link
          href="/"
          className="flex items-center space-x-1.5 hover:text-amber-600 transition-colors py-1 group"
        >
          <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" />
          <span>Return to Journal Frontpage</span>
        </Link>

        <span className="uppercase tracking-wider font-semibold text-amber-700 dark:text-amber-400">
          [{post.category}]
        </span>
      </div>

      {/* Header Editorial Block */}
      <header className="max-w-4xl mx-auto space-y-6 text-center sm:text-left mb-10">
        <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          <span
            className="px-2.5 py-1 rounded-full uppercase font-semibold text-amber-700 dark:text-amber-400 border"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            {post.category}
          </span>
          <span>•</span>
          <span className="flex items-center">
            <Calendar className="w-3.5 h-3.5 mr-1 inline" />
            {formattedDate}
          </span>
          <span>•</span>
          <span className="flex items-center">
            <Clock className="w-3.5 h-3.5 mr-1 inline" />
            {post.readTimeMinutes} min read
          </span>
        </div>

        <h1
          className="font-serif text-3xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.15]"
          style={{ color: 'var(--text-main)' }}
        >
          {post.title}
        </h1>

        <p
          className="text-base sm:text-xl font-serif italic leading-relaxed"
          style={{ color: 'var(--text-muted)' }}
        >
          "{post.excerpt}"
        </p>

        {/* Author Byline & Action Dock */}
        <div
          className="pt-6 border-t flex flex-col sm:flex-row items-center justify-between gap-4"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center space-x-3.5">
            <img
              src={post.author.avatar}
              alt={post.author.name}
              className="w-12 h-12 rounded-full object-cover border"
              style={{ borderColor: 'var(--border-subtle)' }}
            />
            <div className="text-left">
              <h4 className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>
                {post.author.name}
              </h4>
              <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                {post.author.role}
              </p>
            </div>
          </div>

          {/* Action Dock */}
          <div className="flex items-center space-x-2.5">
            <ClapButton postId={post.id} initialClaps={post.claps} />
            <BookmarkButton postId={post.id} />
            <ShareButton />
          </div>
        </div>
      </header>

      {/* Featured Cover Image */}
      {post.coverImage && (
        <div className="max-w-5xl mx-auto my-10 rounded-2xl overflow-hidden border shadow-lg" style={{ borderColor: 'var(--border-subtle)' }}>
          <img
            src={post.coverImage}
            alt={post.title}
            className="w-full max-h-[520px] object-cover"
          />
        </div>
      )}

      {/* Main Reading Grid */}
      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 mt-10">
        {/* Article Body Column */}
        <div className="lg:col-span-8">
          <div
            className="editorial-prose prose-drop-cap font-sans"
            dangerouslySetInnerHTML={{ __html: contentHtml }}
          />

          {/* Tags Cloud */}
          <div className="mt-12 pt-6 border-t space-y-2" style={{ borderColor: 'var(--border-subtle)' }}>
            <span className="text-xs font-mono uppercase tracking-wider block" style={{ color: 'var(--text-faint)' }}>
              Taxonomy Keys:
            </span>
            <div className="flex flex-wrap gap-2">
              {post.tags.map((tag) => (
                <Link
                  key={tag}
                  href={`/?tag=${encodeURIComponent(tag)}`}
                  className="px-3 py-1 rounded-md text-xs font-mono border hover:border-amber-500 transition-colors"
                  style={{
                    backgroundColor: 'var(--bg-subtle)',
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-main)'
                  }}
                >
                  #{tag}
                </Link>
              ))}
            </div>
          </div>

          {/* Author Extended Profile Box */}
          <div
            className="mt-12 p-6 rounded-2xl border flex flex-col sm:flex-row items-center sm:items-start gap-5"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <img
              src={post.author.avatar}
              alt={post.author.name}
              className="w-16 h-16 rounded-full object-cover border flex-shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            />
            <div className="space-y-2 text-center sm:text-left">
              <span className="text-[11px] font-mono uppercase tracking-wider text-amber-700 dark:text-amber-400">
                Author Profile
              </span>
              <h4 className="text-base font-serif font-bold" style={{ color: 'var(--text-main)' }}>
                {post.author.name}
              </h4>
              <p className="text-xs sm:text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                {post.author.bio}
              </p>
            </div>
          </div>

          {/* Adsterra Native Recommendations Banner */}
          <NativeBanner />

          {/* Reader Comments Section */}
          <CommentsSection postId={post.id} initialComments={comments} />
        </div>

        {/* Aside Sidebar */}
        <div className="lg:col-span-4 space-y-8">
          <div className="sticky top-6 space-y-8">
            {/* Table of Contents */}
            <TableOfContents content={post.content} />

            {/* Sidebar Ad Unit (300x250 Medium Rectangle) */}
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

            {/* Next Dispatches */}
            {relatedPosts.length > 0 && (
              <div
                className="p-5 rounded-xl border space-y-4"
                style={{
                  backgroundColor: 'var(--bg-card)',
                  borderColor: 'var(--border-subtle)'
                }}
              >
                <span className="text-xs font-mono uppercase tracking-wider font-semibold text-amber-700 dark:text-amber-400 block">
                  Next in The Journal
                </span>

                <div className="space-y-3">
                  {relatedPosts.map((rel) => (
                    <Link
                      key={rel.id}
                      href={`/post/${rel.slug}`}
                      className="group block space-y-1 transition-colors"
                    >
                      <h5
                        className="text-xs sm:text-sm font-serif font-bold leading-snug group-hover:text-amber-600 transition-colors line-clamp-2"
                        style={{ color: 'var(--text-main)' }}
                      >
                        {rel.title}
                      </h5>
                      <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                        {rel.readTimeMinutes} min read • #{rel.category}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Smartlink Promo in reader sidebar */}
            <SmartlinkPromo />
          </div>
        </div>
      </div>
    </article>
  );
}

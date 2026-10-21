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
import { CommentsSection } from '@/components/CommentsSection';
import { Clock, Calendar, ArrowLeft, ShieldCheck, Terminal, Hash, Cpu, CheckCircle2 } from 'lucide-react';
import { StepProgressBar } from '@/components/shortlink/StepProgressBar';
import { CountdownGateway } from '@/components/shortlink/CountdownGateway';
import { STEP_ARTICLES } from '@/lib/step-content';

export async function generateMetadata({
  params,
  searchParams
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  const { slug } = await params;
  const { step: stepQuery } = await searchParams;
  const step = Math.min(4, Math.max(1, parseInt(stepQuery || '1', 10) || 1));
  const post = getPostBySlug(slug);
  if (!post) return { title: 'Post Not Found — Chronicle' };

  const stepData = STEP_ARTICLES[step] || STEP_ARTICLES[1];

  return {
    title: `[Step ${step}/4] ${stepData.phaseTitle} — ${post.title}`,
    description: stepData.summary
  };
}

export default async function PostPage({
  params,
  searchParams
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  const { slug } = await params;
  const { step: stepQuery } = await searchParams;
  const currentStep = Math.min(4, Math.max(1, parseInt(stepQuery || '1', 10) || 1));
  const post = getPostBySlug(slug);

  if (!post) {
    notFound();
  }

  // Increment view count
  incrementViews(post.slug);
  const comments = getComments(post.id);

  // Load step-specific authentic technical article
  const stepArticle = STEP_ARTICLES[currentStep] || STEP_ARTICLES[1];
  const stepContentHtml = await marked.parse(stepArticle.markdownContent);

  // Convert main post content
  const postContentHtml = await marked.parse(post.content);

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

      {/* Back button & Gateway Breadcrumb */}
      <div className="mb-6 flex flex-wrap items-center justify-between text-xs font-mono gap-2" style={{ color: 'var(--text-muted)' }}>
        <Link
          href="/"
          className="flex items-center space-x-1.5 hover:text-amber-600 transition-colors py-1 group"
        >
          <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" />
          <span>Return to Frontpage</span>
        </Link>

        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 rounded-sm bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30 font-semibold uppercase text-[10px]">
            Shortlink Protocol: Step {currentStep} of 4
          </span>
          <span className="uppercase tracking-wider font-semibold text-neutral-500">
            [{post.category}]
          </span>
        </div>
      </div>

      {/* 4-Layer Step Progress Bar Component */}
      <StepProgressBar currentStep={currentStep} slug={slug} />

      {/* Header Editorial Block */}
      <header className="max-w-4xl mx-auto space-y-5 text-center sm:text-left mb-8">
        <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2 text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          <span
            className="px-2.5 py-1 rounded-full uppercase font-semibold text-amber-700 dark:text-amber-400 border"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            {stepArticle.badge}
          </span>
          <span>•</span>
          <span className="flex items-center">
            <Clock className="w-3.5 h-3.5 mr-1 inline" />
            {stepArticle.estimatedReadTime}
          </span>
          <span>•</span>
          <span className="flex items-center">
            <Calendar className="w-3.5 h-3.5 mr-1 inline" />
            {formattedDate}
          </span>
        </div>

        <h1
          className="font-serif text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight leading-[1.2]"
          style={{ color: 'var(--text-main)' }}
        >
          {stepArticle.headline}
        </h1>

        <p
          className="text-sm sm:text-lg font-serif italic leading-relaxed"
          style={{ color: 'var(--text-muted)' }}
        >
          "{stepArticle.summary}"
        </p>

        {/* Technical Diagnostics Metadata Bar */}
        <div
          className="p-3.5 rounded-xl border grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px] font-mono text-left"
          style={{
            backgroundColor: 'var(--bg-subtle)',
            borderColor: 'var(--border-subtle)'
          }}
        >
          <div>
            <span className="text-neutral-400 block text-[9px] uppercase tracking-wider">Subsystem</span>
            <span className="font-semibold text-amber-600 dark:text-amber-400 truncate block">
              {stepArticle.technicalMetadata.protocol}
            </span>
          </div>
          <div>
            <span className="text-neutral-400 block text-[9px] uppercase tracking-wider">Target Runtime</span>
            <span className="truncate block" style={{ color: 'var(--text-main)' }}>
              {stepArticle.technicalMetadata.targetRuntime}
            </span>
          </div>
          <div>
            <span className="text-neutral-400 block text-[9px] uppercase tracking-wider">Security State</span>
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold truncate block">
              ✓ {stepArticle.technicalMetadata.securityCheck}
            </span>
          </div>
          <div>
            <span className="text-neutral-400 block text-[9px] uppercase tracking-wider">Payload Checksum</span>
            <span className="truncate block opacity-75 font-mono text-[10px]">
              {stepArticle.technicalMetadata.integrityHash.slice(0, 18)}...
            </span>
          </div>
        </div>
      </header>

      {/* Main Reading & Gateway Grid */}
      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 mt-6">
        {/* Article Body Column */}
        <div className="lg:col-span-8 space-y-6">
          {/* Authentic Technical Article for the Current Step */}
          <div
            className="editorial-prose prose-drop-cap font-sans"
            dangerouslySetInnerHTML={{ __html: stepContentHtml }}
          />

          {/* Interactive 8-Second Countdown Gateway Controller */}
          <CountdownGateway
            currentStep={currentStep}
            totalSteps={4}
            slug={slug}
            destinationUrl="https://modapk.org/"
            durationSeconds={8}
          />

          {/* Contextual Context Post Intro (Step 1 only) */}
          {currentStep === 1 && (
            <div
              className="mt-8 p-5 rounded-xl border border-dashed text-xs leading-relaxed"
              style={{
                backgroundColor: 'var(--bg-subtle)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-muted)'
              }}
            >
              <span className="font-mono uppercase font-semibold text-amber-700 dark:text-amber-400 block mb-1">
                Contextual Host Dispatch: {post.title}
              </span>
              <p>{post.excerpt}</p>
            </div>
          )}

          {/* Author Profile */}
          <div
            className="mt-10 p-5 rounded-xl border flex flex-col sm:flex-row items-center sm:items-start gap-4"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <img
              src={post.author.avatar}
              alt={post.author.name}
              className="w-14 h-14 rounded-full object-cover border flex-shrink-0"
              style={{ borderColor: 'var(--border-subtle)' }}
            />
            <div className="space-y-1.5 text-center sm:text-left">
              <span className="text-[10px] font-mono uppercase tracking-wider text-amber-700 dark:text-amber-400">
                Verified Cryptographic Author
              </span>
              <h4 className="text-sm font-serif font-bold" style={{ color: 'var(--text-main)' }}>
                {post.author.name}
              </h4>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                {post.author.bio}
              </p>
            </div>
          </div>

          {/* Reader Comments Section */}
          <CommentsSection postId={post.id} initialComments={comments} />
        </div>

        {/* Aside Sidebar */}
        <div className="lg:col-span-4 space-y-6">
          <div className="sticky top-6 space-y-6">
            {/* Step Navigation Quick Overview */}
            <div
              className="p-5 rounded-xl border space-y-3"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span className="text-xs font-mono uppercase tracking-wider font-semibold text-amber-700 dark:text-amber-400 block">
                Gateway Layers Overview
              </span>

              <div className="space-y-2 text-xs font-mono">
                {[
                  { num: 1, label: 'Manifest & Header Audit' },
                  { num: 2, label: 'DEX Bytecode & Smali' },
                  { num: 3, label: 'SELinux & Sandboxing' },
                  { num: 4, label: 'Destination Clearance (modapk.org)' }
                ].map((s) => {
                  const isCurrent = s.num === currentStep;
                  const isPast = s.num < currentStep;
                  return (
                    <div
                      key={s.num}
                      className={`p-2 rounded-lg border flex items-center justify-between transition-colors ${
                        isCurrent
                          ? 'border-amber-500 bg-amber-500/10 font-bold'
                          : isPast
                          ? 'border-emerald-500/40 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400'
                          : 'opacity-50 border-transparent'
                      }`}
                      style={{
                        borderColor: isCurrent ? 'var(--accent)' : undefined
                      }}
                    >
                      <div className="flex items-center space-x-2">
                        <span className="text-[10px] w-4 h-4 rounded-full flex items-center justify-center bg-black/5 dark:bg-white/10">
                          {s.num}
                        </span>
                        <span className="truncate">{s.label}</span>
                      </div>
                      {isPast ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                      ) : isCurrent ? (
                        <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse flex-shrink-0" />
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Related Dispatches */}
            {relatedPosts.length > 0 && (
              <div
                className="p-5 rounded-xl border space-y-4"
                style={{
                  backgroundColor: 'var(--bg-card)',
                  borderColor: 'var(--border-subtle)'
                }}
              >
                <span className="text-xs font-mono uppercase tracking-wider font-semibold text-amber-700 dark:text-amber-400 block">
                  Related Architecture Dispatches
                </span>

                <div className="space-y-3">
                  {relatedPosts.map((rel) => (
                    <Link
                      key={rel.id}
                      href={`/post/${rel.slug}?step=1`}
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
          </div>
        </div>
      </div>
    </article>
  );
}

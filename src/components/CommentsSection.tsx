'use client';

import React, { useState } from 'react';
import { Comment } from '@/lib/types';
import { MessageSquare, Send, CheckCircle2, User } from 'lucide-react';

interface CommentsSectionProps {
  postId: string;
  initialComments: Comment[];
}

export function CommentsSection({ postId, initialComments }: CommentsSectionProps) {
  const [comments, setComments] = useState<Comment[]>(initialComments);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [content, setContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedMessage, setSubmittedMessage] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim() || !name.trim()) return;

    setIsSubmitting(true);

    const optimisticComment: Comment = {
      id: `comm-temp-${Date.now()}`,
      postId,
      authorName: name.trim(),
      authorEmail: email.trim() || undefined,
      authorAvatar: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=120&q=80',
      content: content.trim(),
      createdAt: new Date().toISOString(),
      likes: 0
    };

    setComments((prev) => [optimisticComment, ...prev]);
    setContent('');
    setSubmittedMessage(true);
    setTimeout(() => setSubmittedMessage(false), 4000);

    try {
      const res = await fetch(`/api/posts/${postId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          authorName: name.trim(),
          authorEmail: email.trim(),
          content: optimisticComment.content
        })
      });

      const data = await res.json();
      if (data.success && data.comment) {
        setComments((prev) =>
          prev.map((c) => (c.id === optimisticComment.id ? data.comment : c))
        );
      }
    } catch (err) {
      console.error('Failed to submit comment:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section id="comments" className="mt-16 pt-12 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center space-x-2">
          <MessageSquare className="w-5 h-5 text-amber-600" />
          <h3 className="font-serif text-2xl font-bold tracking-tight" style={{ color: 'var(--text-main)' }}>
            Discourse & Reader Notes ({comments.length})
          </h3>
        </div>
        <span className="text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
          Civil Discourse
        </span>
      </div>

      {/* Comment Form */}
      <div
        className="p-6 rounded-2xl border mb-10 transition-all duration-200"
        style={{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <h4 className="text-sm font-serif font-bold mb-4" style={{ color: 'var(--text-main)' }}>
          Contribute a perspective to this dispatch
        </h4>

        {submittedMessage && (
          <div
            className="mb-4 p-3 rounded-lg border flex items-center space-x-2 text-xs font-mono text-emerald-600 dark:text-emerald-400 animate-fadeIn"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>Your note has been etched into the dispatch ledger.</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                Your Name / Call-sign *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Eleanor Vance"
                className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border outline-none font-sans"
                style={{
                  borderColor: 'var(--border-subtle)',
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-main)'
                }}
              />
            </div>

            <div>
              <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                Email (Optional, not publicized)
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="eleanor@studio.net"
                className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border outline-none font-sans"
                style={{
                  borderColor: 'var(--border-subtle)',
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-main)'
                }}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
              Your Note / Reflection *
            </label>
            <textarea
              required
              rows={3}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Offer an insight, counter-argument, or corroboration..."
              className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border outline-none font-sans resize-y"
              style={{
                borderColor: 'var(--border-subtle)',
                backgroundColor: 'var(--bg-subtle)',
                color: 'var(--text-main)'
              }}
            />
          </div>

          <div className="flex justify-between items-center pt-2">
            <span className="text-[11px] font-mono" style={{ color: 'var(--text-faint)' }}>
              Markdown supported • Be courteous
            </span>
            <button
              type="submit"
              disabled={isSubmitting || !content.trim() || !name.trim()}
              className="px-4 py-2 rounded-lg text-xs font-mono font-medium text-white flex items-center space-x-1.5 cursor-pointer disabled:opacity-50 transition-opacity"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <span>{isSubmitting ? 'Inscribing...' : 'Publish Note'}</span>
              <Send className="w-3 h-3" />
            </button>
          </div>
        </form>
      </div>

      {/* Comments List */}
      <div className="space-y-4">
        {comments.map((comm) => {
          const dateStr = new Date(comm.createdAt).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
          });

          return (
            <div
              key={comm.id}
              className="p-5 rounded-xl border space-y-3 transition-all"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <img
                    src={comm.authorAvatar}
                    alt={comm.authorName}
                    className="w-8 h-8 rounded-full object-cover border"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  />
                  <div>
                    <h5 className="text-xs sm:text-sm font-semibold leading-tight" style={{ color: 'var(--text-main)' }}>
                      {comm.authorName}
                    </h5>
                    <span className="text-[11px] font-mono leading-tight" style={{ color: 'var(--text-muted)' }}>
                      {dateStr}
                    </span>
                  </div>
                </div>
              </div>

              <p className="text-xs sm:text-sm leading-relaxed font-sans" style={{ color: 'var(--text-muted)' }}>
                {comm.content}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

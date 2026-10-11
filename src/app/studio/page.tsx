'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { marked } from 'marked';
import { Post, SiteStats } from '@/lib/types';
import {
  PenTool,
  BookOpen,
  BarChart3,
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Sparkles,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Eye,
  Heart,
  Calendar,
  Image as ImageIcon,
  Tag as TagIcon,
  Bold,
  Italic,
  Heading2,
  Heading3,
  Quote,
  Code,
  ArrowLeft
} from 'lucide-react';

const COVER_PRESETS = [
  {
    name: 'Typographic & Books',
    url: 'https://images.unsplash.com/photo-1507842229451-7f01be8860ee?auto=format&fit=crop&w=1600&q=80'
  },
  {
    name: 'Minimal Architecture',
    url: 'https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=1600&q=80'
  },
  {
    name: 'Misty Foliage & Nature',
    url: 'https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1600&q=80'
  },
  {
    name: 'Abstract Fluid Dynamics',
    url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1600&q=80'
  },
  {
    name: 'Ink & Paper Library',
    url: 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=1600&q=80'
  },
  {
    name: 'Matrix & Cybernetics',
    url: 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1600&q=80'
  }
];

export default function StudioPage() {
  const [activeTab, setActiveTab] = useState<'stories' | 'compose' | 'analytics'>('stories');
  const [posts, setPosts] = useState<Post[]>([]);
  const [stats, setStats] = useState<SiteStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<'all' | 'published' | 'draft'>('all');
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Editor State
  const [editingPostId, setEditingPostId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [slug, setSlug] = useState('');
  const [excerpt, setExcerpt] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('Design & Craft');
  const [tagsInput, setTagsInput] = useState('');
  const [coverImage, setCoverImage] = useState(COVER_PRESETS[0].url);
  const [status, setStatus] = useState<'published' | 'draft'>('published');
  const [isFeatured, setIsFeatured] = useState(false);
  const [authorName, setAuthorName] = useState('Julian Vance');
  const [previewMode, setPreviewMode] = useState<'edit' | 'preview'>('edit');
  const [renderedPreview, setRenderedPreview] = useState('');

  // Fetch initial data
  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [postsRes, statsRes] = await Promise.all([
        fetch('/api/posts?status=all'),
        fetch('/api/stats')
      ]);

      const postsData = await postsRes.json();
      const statsData = await statsRes.json();

      if (postsData.success) {
        setPosts(postsData.posts);
      }
      if (statsData.success) {
        setStats(statsData.stats);
      }
    } catch (err) {
      console.error('Failed to load studio data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Update preview html whenever content changes
  useEffect(() => {
    if (previewMode === 'preview') {
      const res = marked.parse(content || '*No content written yet.*');
      if (typeof res === 'string') {
        setRenderedPreview(res);
      } else {
        res.then((html) => setRenderedPreview(html));
      }
    }
  }, [content, previewMode]);

  const showNotify = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 4000);
  };

  // Reset Composer form
  const resetForm = () => {
    setEditingPostId(null);
    setTitle('');
    setSlug('');
    setExcerpt('');
    setContent('');
    setCategory('Design & Craft');
    setTagsInput('');
    setCoverImage(COVER_PRESETS[0].url);
    setStatus('published');
    setIsFeatured(false);
    setAuthorName('Julian Vance');
    setPreviewMode('edit');
  };

  const handleEditPost = (post: Post) => {
    setEditingPostId(post.id);
    setTitle(post.title);
    setSlug(post.slug);
    setExcerpt(post.excerpt);
    setContent(post.content);
    setCategory(post.category);
    setTagsInput(post.tags.join(', '));
    setCoverImage(post.coverImage);
    setStatus(post.status);
    setIsFeatured(post.isFeatured);
    setAuthorName(post.author.name);
    setActiveTab('compose');
  };

  const handleDeletePost = async (id: string, titleStr: string) => {
    if (!confirm(`Are you sure you want to delete "${titleStr}"?`)) return;

    try {
      const res = await fetch(`/api/posts/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showNotify('success', 'Dispatch deleted successfully.');
        fetchData();
      } else {
        showNotify('error', 'Failed to delete dispatch.');
      }
    } catch {
      showNotify('error', 'Network error deleting dispatch.');
    }
  };

  const handleToggleStatus = async (post: Post) => {
    const nextStatus = post.status === 'published' ? 'draft' : 'published';
    try {
      const res = await fetch(`/api/posts/${post.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus })
      });
      const data = await res.json();
      if (data.success) {
        showNotify('success', `Status updated to ${nextStatus}.`);
        fetchData();
      }
    } catch {
      showNotify('error', 'Error updating status.');
    }
  };

  const handleSavePost = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) {
      showNotify('error', 'Title and content are required.');
      return;
    }

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const payload = {
      title: title.trim(),
      slug: slug.trim() || undefined,
      excerpt: excerpt.trim(),
      content: content.trim(),
      category: category.trim(),
      tags: tags.length > 0 ? tags : ['Editorial'],
      coverImage,
      status,
      isFeatured,
      author: {
        name: authorName.trim() || 'Editorial Staff',
        avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
        role: 'Contributing Editor',
        bio: 'Inquiries into software craft and typography.'
      }
    };

    try {
      if (editingPostId) {
        const res = await fetch(`/api/posts/${editingPostId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          showNotify('success', 'Dispatch updated successfully.');
          fetchData();
          setActiveTab('stories');
          resetForm();
        }
      } else {
        const res = await fetch('/api/posts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          showNotify('success', 'New dispatch inscribed & published.');
          fetchData();
          setActiveTab('stories');
          resetForm();
        }
      }
    } catch {
      showNotify('error', 'Network error saving dispatch.');
    }
  };

  const handleResetSeedData = async () => {
    if (!confirm('Re-seed initial demo editorial essays? Any modifications will be replaced with fresh authentic dispatches.')) return;

    try {
      const res = await fetch('/api/seed', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showNotify('success', 'Database regenerated with initial editorial seed.');
        fetchData();
      }
    } catch {
      showNotify('error', 'Failed to seed data.');
    }
  };

  // Helper to insert markdown tags into content
  const insertMarkdown = (prefix: string, suffix: string = '') => {
    setContent((prev) => `${prev}\n${prefix}Text${suffix}\n`);
  };

  const filteredPosts = posts.filter((p) => {
    if (statusFilter === 'all') return true;
    return p.status === statusFilter;
  });

  return (
    <div className="animate-fadeIn space-y-8 pb-16">
      {/* Studio Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b pb-6" style={{ borderColor: 'var(--border-subtle)' }}>
        <div>
          <div className="flex items-center space-x-2 text-xs font-mono uppercase tracking-widest text-amber-700 dark:text-amber-400 font-semibold">
            <Sparkles className="w-4 h-4" />
            <span>Chronicle Publishing Studio</span>
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold tracking-tight mt-1" style={{ color: 'var(--text-main)' }}>
            Editorial Desk & CMS
          </h1>
          <p className="text-xs sm:text-sm font-sans" style={{ color: 'var(--text-muted)' }}>
            Compose, manage, and curate sovereign digital dispatches with instant reactivity.
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <button
            onClick={handleResetSeedData}
            className="px-3 py-1.5 rounded-lg border text-xs font-mono transition-colors flex items-center space-x-1.5 cursor-pointer hover:border-amber-500"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-main)'
            }}
            title="Reset database to seed articles"
          >
            <RotateCcw className="w-3.5 h-3.5 text-amber-600" />
            <span>Reset Demo Data</span>
          </button>

          <Link
            href="/"
            className="px-3.5 py-1.5 rounded-lg border text-xs font-mono transition-colors flex items-center space-x-1.5 cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-main)'
            }}
          >
            <span>View Publication</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Toast Notification */}
      {notification && (
        <div
          className={`p-3.5 rounded-xl border flex items-center space-x-2 text-xs font-mono animate-fadeIn ${
            notification.type === 'success'
              ? 'text-emerald-700 dark:text-emerald-300 border-emerald-500/30 bg-emerald-500/10'
              : 'text-rose-700 dark:text-rose-300 border-rose-500/30 bg-rose-500/10'
          }`}
        >
          {notification.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
          )}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center space-x-2 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <button
          onClick={() => setActiveTab('stories')}
          className={`px-4 py-2.5 text-xs sm:text-sm font-mono border-b-2 font-medium transition-all cursor-pointer flex items-center space-x-2 ${
            activeTab === 'stories'
              ? 'border-amber-600 text-amber-700 dark:text-amber-400 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>Story Desk ({posts.length})</span>
        </button>

        <button
          onClick={() => {
            if (activeTab !== 'compose') resetForm();
            setActiveTab('compose');
          }}
          className={`px-4 py-2.5 text-xs sm:text-sm font-mono border-b-2 font-medium transition-all cursor-pointer flex items-center space-x-2 ${
            activeTab === 'compose'
              ? 'border-amber-600 text-amber-700 dark:text-amber-400 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <PenTool className="w-4 h-4" />
          <span>{editingPostId ? 'Edit Dispatch' : 'New Dispatch'}</span>
        </button>

        <button
          onClick={() => setActiveTab('analytics')}
          className={`px-4 py-2.5 text-xs sm:text-sm font-mono border-b-2 font-medium transition-all cursor-pointer flex items-center space-x-2 ${
            activeTab === 'analytics'
              ? 'border-amber-600 text-amber-700 dark:text-amber-400 font-bold'
              : 'border-transparent text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          <span>Analytics & Telemetry</span>
        </button>
      </div>

      {/* TAB 1: STORY DESK */}
      {activeTab === 'stories' && (
        <div className="space-y-6">
          {/* Desk Filter Bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                Filter:
              </span>
              {(['all', 'published', 'draft'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono uppercase cursor-pointer ${
                    statusFilter === st
                      ? 'bg-amber-600 text-white font-bold'
                      : 'border hover:border-amber-500'
                  }`}
                  style={{
                    borderColor: 'var(--border-subtle)',
                    color: statusFilter === st ? '#ffffff' : 'var(--text-main)',
                    backgroundColor: statusFilter === st ? 'var(--accent)' : 'var(--bg-card)'
                  }}
                >
                  {st}
                </button>
              ))}
            </div>

            <button
              onClick={() => {
                resetForm();
                setActiveTab('compose');
              }}
              className="px-3.5 py-1.5 rounded-lg text-xs font-mono font-medium text-white flex items-center space-x-1.5 cursor-pointer shadow-xs"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Compose Dispatch</span>
            </button>
          </div>

          {/* Posts Table */}
          <div
            className="rounded-2xl border overflow-hidden"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr
                    className="border-b font-mono text-[11px] uppercase tracking-wider"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-muted)'
                    }}
                  >
                    <th className="py-3 px-4">Title & Details</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Telemetry</th>
                    <th className="py-3 px-4">Date</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
                  {filteredPosts.map((p) => (
                    <tr
                      key={p.id}
                      className="hover:bg-amber-500/5 transition-colors"
                      style={{ color: 'var(--text-main)' }}
                    >
                      <td className="py-3.5 px-4 max-w-xs sm:max-w-md">
                        <div className="font-serif font-bold text-sm line-clamp-1">{p.title}</div>
                        <div className="text-[11px] font-mono text-gray-500 truncate mt-0.5">
                          slug: /{p.slug} {p.isFeatured && <span className="text-amber-600 font-bold">• [Featured]</span>}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-xs">
                        <span className="px-2 py-0.5 rounded border" style={{ borderColor: 'var(--border-subtle)' }}>
                          {p.category}
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        <button
                          onClick={() => handleToggleStatus(p)}
                          className={`px-2 py-0.5 rounded-full font-mono text-[10px] uppercase font-semibold cursor-pointer border ${
                            p.status === 'published'
                              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                              : 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                          }`}
                          title="Click to toggle status"
                        >
                          {p.status}
                        </button>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-[11px] space-x-3 text-gray-500">
                        <span>{p.views} views</span>
                        <span>{p.claps} claps</span>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-[11px] text-gray-500 whitespace-nowrap">
                        {new Date(p.createdAt).toLocaleDateString()}
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <div className="inline-flex items-center space-x-1">
                          <Link
                            href={`/post/${p.slug}`}
                            target="_blank"
                            className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 cursor-pointer"
                            title="View Public Post"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Link>
                          <button
                            onClick={() => handleEditPost(p)}
                            className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-amber-600 cursor-pointer"
                            title="Edit Post"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeletePost(p.id, p.title)}
                            className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-rose-500 cursor-pointer"
                            title="Delete Post"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: COMPOSER / EDITOR */}
      {activeTab === 'compose' && (
        <form onSubmit={handleSavePost} className="space-y-6">
          <div
            className="p-6 sm:p-8 rounded-2xl border space-y-6"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <div className="flex items-center justify-between border-b pb-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <div>
                <h3 className="font-serif text-xl font-bold" style={{ color: 'var(--text-main)' }}>
                  {editingPostId ? 'Revise Journal Dispatch' : 'Compose New Journal Dispatch'}
                </h3>
                <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                  Write markdown with live side-by-side verification.
                </p>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => setPreviewMode(previewMode === 'edit' ? 'preview' : 'edit')}
                  className="px-3 py-1.5 rounded-lg border text-xs font-mono cursor-pointer flex items-center space-x-1"
                  style={{
                    backgroundColor: 'var(--bg-subtle)',
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-main)'
                  }}
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>{previewMode === 'edit' ? 'Preview' : 'Editor'}</span>
                </button>
              </div>
            </div>

            {/* Title & Slug */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                  Dispatch Title *
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    if (!editingPostId) {
                      setSlug(
                        e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9]+/g, '-')
                          .replace(/(^-|-$)/g, '')
                      );
                    }
                  }}
                  placeholder="e.g. The Architecture of Quiet Software"
                  className="w-full px-4 py-2.5 text-base sm:text-lg font-serif font-bold rounded-xl border outline-none"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    backgroundColor: 'var(--bg-subtle)',
                    color: 'var(--text-main)'
                  }}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                    Slug URI (auto-derived)
                  </label>
                  <input
                    type="text"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="architecture-of-quiet-software"
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border outline-none"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                    Category
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border outline-none"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  >
                    <option value="Design & Craft">Design & Craft</option>
                    <option value="Technology">Technology & Systems</option>
                    <option value="Artificial Intelligence">Artificial Intelligence</option>
                    <option value="Culture & Web">Culture & Web</option>
                    <option value="General">General Dispatches</option>
                  </select>
                </div>
              </div>

              {/* Excerpt */}
              <div>
                <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                  Excerpt / Dek (1-2 sentences summarizing the thesis)
                </label>
                <textarea
                  rows={2}
                  value={excerpt}
                  onChange={(e) => setExcerpt(e.target.value)}
                  placeholder="A short, evocative synopsis displayed on cards and search engines..."
                  className="w-full px-3 py-2 text-xs sm:text-sm rounded-lg border outline-none font-sans"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    backgroundColor: 'var(--bg-subtle)',
                    color: 'var(--text-main)'
                  }}
                />
              </div>

              {/* Cover Image Selector */}
              <div>
                <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                  Cover Image URL
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={coverImage}
                    onChange={(e) => setCoverImage(e.target.value)}
                    placeholder="https://images.unsplash.com/..."
                    className="flex-1 px-3 py-2 text-xs font-mono rounded-lg border outline-none"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  />
                </div>

                {/* Preset image thumbnails */}
                <div className="mt-2 flex items-center space-x-2 overflow-x-auto pb-1">
                  <span className="text-[11px] font-mono text-gray-500 whitespace-nowrap">Presets:</span>
                  {COVER_PRESETS.map((cp) => (
                    <button
                      key={cp.name}
                      type="button"
                      onClick={() => setCoverImage(cp.url)}
                      className={`px-2 py-1 rounded text-[10px] font-mono whitespace-nowrap border cursor-pointer ${
                        coverImage === cp.url ? 'bg-amber-600 text-white font-bold' : 'hover:border-amber-500'
                      }`}
                      style={{
                        borderColor: 'var(--border-subtle)',
                        backgroundColor: coverImage === cp.url ? 'var(--accent)' : 'var(--bg-subtle)',
                        color: coverImage === cp.url ? '#fff' : 'var(--text-main)'
                      }}
                    >
                      {cp.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tags & Meta Settings */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
                <div>
                  <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                    Tags (Comma-separated)
                  </label>
                  <input
                    type="text"
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    placeholder="Craftsmanship, Typography, UI"
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border outline-none"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                    Author Name
                  </label>
                  <input
                    type="text"
                    value={authorName}
                    onChange={(e) => setAuthorName(e.target.value)}
                    placeholder="Julian Vance"
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border outline-none"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono mb-1" style={{ color: 'var(--text-muted)' }}>
                    Publication Status
                  </label>
                  <div className="flex items-center space-x-4 pt-2">
                    <label className="flex items-center space-x-1.5 text-xs font-mono cursor-pointer">
                      <input
                        type="radio"
                        name="status"
                        checked={status === 'published'}
                        onChange={() => setStatus('published')}
                      />
                      <span>Published</span>
                    </label>
                    <label className="flex items-center space-x-1.5 text-xs font-mono cursor-pointer">
                      <input
                        type="radio"
                        name="status"
                        checked={status === 'draft'}
                        onChange={() => setStatus('draft')}
                      />
                      <span>Draft</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Featured toggle */}
              <div className="pt-2">
                <label className="flex items-center space-x-2 text-xs font-mono cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isFeatured}
                    onChange={(e) => setIsFeatured(e.target.checked)}
                  />
                  <span>Display as Featured Lead Story on Frontpage</span>
                </label>
              </div>

              {/* Content Editor Toolbar */}
              <div className="pt-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                    Markdown Body *
                  </label>

                  <div className="flex items-center space-x-1">
                    <button
                      type="button"
                      onClick={() => insertMarkdown('**', '**')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Bold"
                    >
                      <Bold className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => insertMarkdown('*', '*')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Italic"
                    >
                      <Italic className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => insertMarkdown('## ')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Heading 2"
                    >
                      <Heading2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => insertMarkdown('### ')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Heading 3"
                    >
                      <Heading3 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => insertMarkdown('> ')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Quote"
                    >
                      <Quote className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => insertMarkdown('```typescript\n', '\n```')}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800"
                      title="Code block"
                    >
                      <Code className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {previewMode === 'edit' ? (
                  <textarea
                    required
                    rows={14}
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Write your thesis in Markdown... (headings ##, code blocks ```, quotes >)"
                    className="w-full p-4 text-xs sm:text-sm font-mono rounded-xl border outline-none leading-relaxed"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-main)'
                    }}
                  />
                ) : (
                  <div
                    className="p-6 rounded-xl border min-h-[300px] editorial-prose"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: 'var(--bg-subtle)'
                    }}
                    dangerouslySetInnerHTML={{ __html: renderedPreview }}
                  />
                )}
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center justify-between border-t pt-6" style={{ borderColor: 'var(--border-subtle)' }}>
              <button
                type="button"
                onClick={() => {
                  resetForm();
                  setActiveTab('stories');
                }}
                className="px-4 py-2 rounded-lg border text-xs font-mono cursor-pointer"
                style={{
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-muted)'
                }}
              >
                Cancel
              </button>

              <button
                type="submit"
                className="px-6 py-2.5 rounded-lg text-xs font-mono font-medium text-white shadow-md cursor-pointer transition-transform hover:scale-105"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {editingPostId ? 'Update & Inscribe Dispatch' : 'Publish to Chronicle'}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* TAB 3: ANALYTICS & INSIGHTS */}
      {activeTab === 'analytics' && stats && (
        <div className="space-y-8">
          {/* Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div
              className="p-5 rounded-2xl border space-y-1"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span className="text-[11px] font-mono uppercase tracking-wider text-gray-500">Total Dispatches</span>
              <div className="font-serif text-3xl font-bold" style={{ color: 'var(--text-main)' }}>
                {stats.totalPosts}
              </div>
              <span className="text-[10px] font-mono text-emerald-600">
                {stats.publishedPosts} published • {stats.draftPosts} drafts
              </span>
            </div>

            <div
              className="p-5 rounded-2xl border space-y-1"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span className="text-[11px] font-mono uppercase tracking-wider text-gray-500">Audience Views</span>
              <div className="font-serif text-3xl font-bold" style={{ color: 'var(--text-main)' }}>
                {stats.totalViews.toLocaleString()}
              </div>
              <span className="text-[10px] font-mono text-blue-500">Across all monographs</span>
            </div>

            <div
              className="p-5 rounded-2xl border space-y-1"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span className="text-[11px] font-mono uppercase tracking-wider text-gray-500">Reader Claps</span>
              <div className="font-serif text-3xl font-bold text-rose-500">
                {stats.totalClaps.toLocaleString()}
              </div>
              <span className="text-[10px] font-mono text-rose-500">Approbation tokens</span>
            </div>

            <div
              className="p-5 rounded-2xl border space-y-1"
              style={{
                backgroundColor: 'var(--bg-card)',
                borderColor: 'var(--border-subtle)'
              }}
            >
              <span className="text-[11px] font-mono uppercase tracking-wider text-gray-500">Reader Notes</span>
              <div className="font-serif text-3xl font-bold text-amber-600">
                {stats.totalComments}
              </div>
              <span className="text-[10px] font-mono text-amber-600">Discourse messages</span>
            </div>
          </div>

          {/* Top Performing Dispatches */}
          <div
            className="p-6 rounded-2xl border space-y-4"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)'
            }}
          >
            <h3 className="font-serif text-lg font-bold" style={{ color: 'var(--text-main)' }}>
              Top Resonating Dispatches
            </h3>

            <div className="space-y-3">
              {stats.topPosts.map((post, index) => (
                <div
                  key={post.id}
                  className="flex items-center justify-between p-3 rounded-xl border border-dashed text-xs"
                  style={{ borderColor: 'var(--border-subtle)' }}
                >
                  <div className="flex items-center space-x-3">
                    <span className="font-mono font-bold text-amber-600">0{index + 1}</span>
                    <div>
                      <h4 className="font-serif font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                        {post.title}
                      </h4>
                      <span className="font-mono text-[11px] text-gray-500">
                        {post.category} • {post.readTimeMinutes}m read
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-4 font-mono text-[11px]">
                    <span className="flex items-center space-x-1 text-gray-500">
                      <Eye className="w-3 h-3 text-blue-500" />
                      <span>{post.views}</span>
                    </span>
                    <span className="flex items-center space-x-1 text-rose-500">
                      <Heart className="w-3 h-3" />
                      <span>{post.claps}</span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

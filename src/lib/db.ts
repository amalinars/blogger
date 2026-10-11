import fs from 'fs';
import path from 'path';
import { Post, Comment, Category, ArchiveItem, SiteStats } from './types';
import { INITIAL_POSTS, INITIAL_COMMENTS } from './seed-data';

interface DatabaseSchema {
  posts: Post[];
  comments: Comment[];
  version: number;
}

const DATA_DIR = path.join(process.cwd(), 'data');
const DB_FILE = path.join(DATA_DIR, 'chronicle-db.json');

function ensureInitialized(): DatabaseSchema {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  if (!fs.existsSync(DB_FILE)) {
    const initialData: DatabaseSchema = {
      posts: INITIAL_POSTS,
      comments: INITIAL_COMMENTS,
      version: 1
    };
    saveData(initialData);
    return initialData;
  }

  try {
    const content = fs.readFileSync(DB_FILE, 'utf-8');
    const data = JSON.parse(content) as DatabaseSchema;
    if (!data.posts || !Array.isArray(data.posts)) {
      throw new Error('Invalid database format');
    }
    return data;
  } catch (error) {
    console.error('Error reading database file, re-initializing seed data:', error);
    const initialData: DatabaseSchema = {
      posts: INITIAL_POSTS,
      comments: INITIAL_COMMENTS,
      version: 1
    };
    saveData(initialData);
    return initialData;
  }
}

function saveData(data: DatabaseSchema): void {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  const tempFile = `${DB_FILE}.${Date.now()}.tmp`;
  fs.writeFileSync(tempFile, JSON.stringify(data, null, 2), 'utf-8');
  fs.renameSync(tempFile, DB_FILE);
}

export function getAllPosts(options?: {
  category?: string;
  tag?: string;
  search?: string;
  status?: 'published' | 'draft' | 'all';
  sort?: 'latest' | 'claps' | 'views';
}): Post[] {
  const db = ensureInitialized();
  let list = [...db.posts];

  // Status filter
  const statusFilter = options?.status ?? 'published';
  if (statusFilter !== 'all') {
    list = list.filter((p) => p.status === statusFilter);
  }

  // Category filter
  if (options?.category) {
    const catLower = options.category.toLowerCase();
    list = list.filter((p) => p.category.toLowerCase() === catLower);
  }

  // Tag filter
  if (options?.tag) {
    const tagLower = options.tag.toLowerCase();
    list = list.filter((p) => p.tags.some((t) => t.toLowerCase() === tagLower));
  }

  // Search filter
  if (options?.search) {
    const query = options.search.toLowerCase().trim();
    list = list.filter(
      (p) =>
        p.title.toLowerCase().includes(query) ||
        p.excerpt.toLowerCase().includes(query) ||
        p.content.toLowerCase().includes(query) ||
        p.tags.some((t) => t.toLowerCase().includes(query)) ||
        p.author.name.toLowerCase().includes(query)
    );
  }

  // Sort
  const sort = options?.sort ?? 'latest';
  if (sort === 'claps') {
    list.sort((a, b) => b.claps - a.claps);
  } else if (sort === 'views') {
    list.sort((a, b) => b.views - a.views);
  } else {
    list.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }

  return list;
}

export function getPostBySlug(slug: string): Post | null {
  const db = ensureInitialized();
  return db.posts.find((p) => p.slug === slug) || null;
}

export function getPostById(id: string): Post | null {
  const db = ensureInitialized();
  return db.posts.find((p) => p.id === id) || null;
}

export function createPost(postInput: Partial<Post>): Post {
  const db = ensureInitialized();

  const title = postInput.title?.trim() || 'Untitled Journal Entry';
  const baseSlug =
    postInput.slug?.trim() ||
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');

  let slug = baseSlug || `post-${Date.now()}`;
  let counter = 1;
  while (db.posts.some((p) => p.slug === slug)) {
    slug = `${baseSlug}-${counter++}`;
  }

  const wordCount = (postInput.content || '').split(/\s+/).length;
  const readTimeMinutes = Math.max(1, Math.ceil(wordCount / 200));

  const newPost: Post = {
    id: `post-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
    slug,
    title,
    excerpt: postInput.excerpt?.trim() || (postInput.content || '').slice(0, 160) + '...',
    content: postInput.content || '',
    coverImage:
      postInput.coverImage ||
      'https://images.unsplash.com/photo-1499750310107-5fef28a66643?auto=format&fit=crop&w=1600&q=80',
    author: postInput.author || {
      name: 'Editorial Staff',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      role: 'Staff Writer',
      bio: 'Dispatches from the Chronicle editorial bureau.'
    },
    category: postInput.category || 'General',
    tags: Array.isArray(postInput.tags) ? postInput.tags : ['Journal'],
    readTimeMinutes,
    views: 0,
    claps: 0,
    status: postInput.status === 'draft' ? 'draft' : 'published',
    isFeatured: Boolean(postInput.isFeatured),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  db.posts.unshift(newPost);
  saveData(db);
  return newPost;
}

export function updatePost(id: string, updates: Partial<Post>): Post | null {
  const db = ensureInitialized();
  const index = db.posts.findIndex((p) => p.id === id);
  if (index === -1) return null;

  const existing = db.posts[index];
  const wordCount = (updates.content ?? existing.content).split(/\s+/).length;
  const readTimeMinutes = Math.max(1, Math.ceil(wordCount / 200));

  const updated: Post = {
    ...existing,
    ...updates,
    id: existing.id,
    readTimeMinutes,
    updatedAt: new Date().toISOString()
  };

  db.posts[index] = updated;
  saveData(db);
  return updated;
}

export function deletePost(id: string): boolean {
  const db = ensureInitialized();
  const initialLength = db.posts.length;
  db.posts = db.posts.filter((p) => p.id !== id);
  db.comments = db.comments.filter((c) => c.postId !== id);
  if (db.posts.length !== initialLength) {
    saveData(db);
    return true;
  }
  return false;
}

export function incrementViews(slug: string): number {
  const db = ensureInitialized();
  const post = db.posts.find((p) => p.slug === slug);
  if (post) {
    post.views = (post.views || 0) + 1;
    saveData(db);
    return post.views;
  }
  return 0;
}

export function incrementClaps(id: string, amount: number = 1): number {
  const db = ensureInitialized();
  const post = db.posts.find((p) => p.id === id || p.slug === id);
  if (post) {
    post.claps = (post.claps || 0) + Math.max(1, amount);
    saveData(db);
    return post.claps;
  }
  return 0;
}

export function getComments(postId: string): Comment[] {
  const db = ensureInitialized();
  return db.comments
    .filter((c) => c.postId === postId)
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function addComment(postId: string, commentInput: {
  authorName: string;
  authorEmail?: string;
  content: string;
}): Comment {
  const db = ensureInitialized();

  // Generate pleasant random avatar if none provided
  const avatarList = [
    'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=120&q=80',
    'https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=120&q=80',
    'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=120&q=80',
    'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=120&q=80'
  ];
  const avatar = avatarList[Math.floor(Math.random() * avatarList.length)];

  const newComment: Comment = {
    id: `comm-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    postId,
    authorName: commentInput.authorName.trim() || 'Anonymous Reader',
    authorEmail: commentInput.authorEmail?.trim() || undefined,
    authorAvatar: avatar,
    content: commentInput.content.trim(),
    createdAt: new Date().toISOString(),
    likes: 0
  };

  db.comments.unshift(newComment);
  saveData(db);
  return newComment;
}

export function getCategories(): Category[] {
  const db = ensureInitialized();
  const published = db.posts.filter((p) => p.status === 'published');
  const catMap = new Map<string, number>();

  for (const post of published) {
    const cat = post.category || 'General';
    catMap.set(cat, (catMap.get(cat) || 0) + 1);
  }

  const categoryDescriptions: Record<string, string> = {
    'Design & Craft': 'Typographic rhythm, tactile digital interfaces, and physical software.',
    'Technology': 'Systems architecture, latency economics, and mechanical sympathy.',
    'Culture & Web': 'The evolution of personal publishing, indie webs, and digital gardens.',
    'Artificial Intelligence': 'Epistemology of neural representations, agentic autonomy, and human taste.',
    'General': 'General musings and varied dispatch notes.'
  };

  return Array.from(catMap.entries()).map(([name, count]) => ({
    id: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    name,
    slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    description: categoryDescriptions[name] || 'Essays and reflections.',
    count
  }));
}

export function getAllTags(): { tag: string; count: number }[] {
  const db = ensureInitialized();
  const published = db.posts.filter((p) => p.status === 'published');
  const tagMap = new Map<string, number>();

  for (const post of published) {
    for (const tag of post.tags) {
      tagMap.set(tag, (tagMap.get(tag) || 0) + 1);
    }
  }

  return Array.from(tagMap.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);
}

export function getArchive(): ArchiveItem[] {
  const db = ensureInitialized();
  const published = db.posts.filter((p) => p.status === 'published');

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const map = new Map<string, ArchiveItem>();

  for (const post of published) {
    const date = new Date(post.createdAt);
    const year = date.getFullYear();
    const monthNumber = date.getMonth();
    const key = `${year}-${monthNumber}`;

    if (!map.has(key)) {
      map.set(key, {
        year,
        month: monthNames[monthNumber],
        monthNumber,
        count: 0,
        posts: []
      });
    }

    const item = map.get(key)!;
    item.count += 1;
    item.posts.push({
      id: post.id,
      slug: post.slug,
      title: post.title,
      createdAt: post.createdAt,
      category: post.category
    });
  }

  return Array.from(map.values()).sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year;
    return b.monthNumber - a.monthNumber;
  });
}

export function getSiteStats(): SiteStats {
  const db = ensureInitialized();
  const totalPosts = db.posts.length;
  const publishedPosts = db.posts.filter((p) => p.status === 'published').length;
  const draftPosts = totalPosts - publishedPosts;
  const totalViews = db.posts.reduce((sum, p) => sum + (p.views || 0), 0);
  const totalClaps = db.posts.reduce((sum, p) => sum + (p.claps || 0), 0);
  const totalComments = db.comments.length;

  const topPosts = [...db.posts]
    .sort((a, b) => (b.views + b.claps * 2) - (a.views + a.claps * 2))
    .slice(0, 5);

  return {
    totalPosts,
    publishedPosts,
    draftPosts,
    totalViews,
    totalClaps,
    totalComments,
    topPosts
  };
}

export function resetSeedData(): void {
  const initialData: DatabaseSchema = {
    posts: INITIAL_POSTS,
    comments: INITIAL_COMMENTS,
    version: 1
  };
  saveData(initialData);
}

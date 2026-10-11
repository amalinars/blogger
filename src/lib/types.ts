export interface Author {
  name: string;
  avatar: string;
  role: string;
  bio: string;
}

export interface Post {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  content: string;
  coverImage: string;
  author: Author;
  category: string;
  tags: string[];
  readTimeMinutes: number;
  views: number;
  claps: number;
  status: 'published' | 'draft';
  isFeatured: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Comment {
  id: string;
  postId: string;
  authorName: string;
  authorEmail?: string;
  authorAvatar: string;
  content: string;
  createdAt: string;
  likes: number;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  description: string;
  count: number;
}

export interface ArchiveItem {
  year: number;
  month: string;
  monthNumber: number;
  count: number;
  posts: {
    id: string;
    slug: string;
    title: string;
    createdAt: string;
    category: string;
  }[];
}

export interface SiteStats {
  totalPosts: number;
  publishedPosts: number;
  draftPosts: number;
  totalViews: number;
  totalClaps: number;
  totalComments: number;
  topPosts: Post[];
}

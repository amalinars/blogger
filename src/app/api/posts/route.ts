import { NextRequest, NextResponse } from 'next/server';
import { getAllPosts, createPost } from '@/lib/db';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const category = searchParams.get('category') || undefined;
    const tag = searchParams.get('tag') || undefined;
    const search = searchParams.get('search') || undefined;
    const status = (searchParams.get('status') as 'published' | 'draft' | 'all') || undefined;
    const sort = (searchParams.get('sort') as 'latest' | 'claps' | 'views') || undefined;

    const posts = getAllPosts({ category, tag, search, status, sort });
    return NextResponse.json({ success: true, posts });
  } catch (error) {
    console.error('Failed to get posts:', error);
    return NextResponse.json({ success: false, error: 'Failed to fetch posts' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    if (!body.title || !body.content) {
      return NextResponse.json(
        { success: false, error: 'Title and content are required' },
        { status: 400 }
      );
    }

    const newPost = createPost(body);
    return NextResponse.json({ success: true, post: newPost }, { status: 201 });
  } catch (error) {
    console.error('Failed to create post:', error);
    return NextResponse.json({ success: false, error: 'Failed to create post' }, { status: 500 });
  }
}

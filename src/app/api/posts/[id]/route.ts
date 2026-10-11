import { NextRequest, NextResponse } from 'next/server';
import { getPostById, getPostBySlug, updatePost, deletePost, incrementViews } from '@/lib/db';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { searchParams } = new URL(request.url);
    const shouldIncrement = searchParams.get('views') === '1';

    let post = getPostBySlug(id);
    if (!post) {
      post = getPostById(id);
    }

    if (!post) {
      return NextResponse.json({ success: false, error: 'Post not found' }, { status: 404 });
    }

    if (shouldIncrement) {
      incrementViews(post.slug);
      post.views += 1;
    }

    return NextResponse.json({ success: true, post });
  } catch (error) {
    console.error('Failed to get post:', error);
    return NextResponse.json({ success: false, error: 'Internal server error' }, { status: 500 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();

    let post = getPostById(id);
    if (!post) {
      post = getPostBySlug(id);
    }

    if (!post) {
      return NextResponse.json({ success: false, error: 'Post not found' }, { status: 404 });
    }

    const updated = updatePost(post.id, body);
    return NextResponse.json({ success: true, post: updated });
  } catch (error) {
    console.error('Failed to update post:', error);
    return NextResponse.json({ success: false, error: 'Failed to update post' }, { status: 500 });
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    let post = getPostById(id);
    if (!post) {
      post = getPostBySlug(id);
    }

    if (!post) {
      return NextResponse.json({ success: false, error: 'Post not found' }, { status: 404 });
    }

    const deleted = deletePost(post.id);
    return NextResponse.json({ success: deleted });
  } catch (error) {
    console.error('Failed to delete post:', error);
    return NextResponse.json({ success: false, error: 'Failed to delete post' }, { status: 500 });
  }
}

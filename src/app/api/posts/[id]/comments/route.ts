import { NextRequest, NextResponse } from 'next/server';
import { getComments, addComment, getPostById, getPostBySlug } from '@/lib/db';

export async function GET(
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

    const comments = getComments(post.id);
    return NextResponse.json({ success: true, comments });
  } catch (error) {
    console.error('Failed to get comments:', error);
    return NextResponse.json({ success: false, error: 'Internal server error' }, { status: 500 });
  }
}

export async function POST(
  request: NextRequest,
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

    const body = await request.json();
    if (!body.content || !body.content.trim()) {
      return NextResponse.json(
        { success: false, error: 'Comment content is required' },
        { status: 400 }
      );
    }

    const comment = addComment(post.id, {
      authorName: body.authorName || 'Curious Reader',
      authorEmail: body.authorEmail,
      content: body.content
    });

    return NextResponse.json({ success: true, comment }, { status: 201 });
  } catch (error) {
    console.error('Failed to add comment:', error);
    return NextResponse.json({ success: false, error: 'Failed to post comment' }, { status: 500 });
  }
}

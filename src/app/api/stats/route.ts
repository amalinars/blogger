import { NextResponse } from 'next/server';
import { getSiteStats, getCategories, getAllTags, getArchive } from '@/lib/db';

export async function GET() {
  try {
    const stats = getSiteStats();
    const categories = getCategories();
    const tags = getAllTags();
    const archive = getArchive();

    return NextResponse.json({
      success: true,
      stats,
      categories,
      tags,
      archive
    });
  } catch (error) {
    console.error('Failed to get stats:', error);
    return NextResponse.json({ success: false, error: 'Internal server error' }, { status: 500 });
  }
}

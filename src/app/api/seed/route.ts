import { NextResponse } from 'next/server';
import { resetSeedData } from '@/lib/db';

export async function POST() {
  try {
    resetSeedData();
    return NextResponse.json({ success: true, message: 'Database reset to initial editorial seed data.' });
  } catch (error) {
    console.error('Failed to reset seed data:', error);
    return NextResponse.json({ success: false, error: 'Failed to reset seed data' }, { status: 500 });
  }
}

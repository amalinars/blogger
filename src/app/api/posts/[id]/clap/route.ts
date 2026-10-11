import { NextRequest, NextResponse } from 'next/server';
import { incrementClaps } from '@/lib/db';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    let amount = 1;

    try {
      const body = await request.json();
      if (typeof body.amount === 'number' && body.amount > 0) {
        amount = body.amount;
      }
    } catch {
      // Default to 1 if no json body
    }

    const claps = incrementClaps(id, amount);
    return NextResponse.json({ success: true, claps });
  } catch (error) {
    console.error('Failed to increment claps:', error);
    return NextResponse.json({ success: false, error: 'Failed to record clap' }, { status: 500 });
  }
}

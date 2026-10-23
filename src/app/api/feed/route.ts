import { getFeed } from '@/lib/feed';

export const dynamic = 'force-dynamic';

export async function GET() {
  const feed = await getFeed();

  return Response.json(feed, {
    headers: {
      'Cache-Control': 'public, s-maxage=900, stale-while-revalidate=1800',
    },
  });
}

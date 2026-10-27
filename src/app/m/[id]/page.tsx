import { MonetagExperience } from '@/components/monetag-experience';
import { getFeed } from '@/lib/feed';
import { DESTINATION } from '@/lib/site-config';

export const revalidate = 900;

export default async function MonetagGatePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const feed = await getFeed();

  return (
    <MonetagExperience
      slug={id}
      steps={feed.steps}
      destination={DESTINATION}
    />
  );
}

import { HilltopExperience } from '@/components/hilltop-experience';
import { getFeed } from '@/lib/feed';
import { DESTINATION } from '@/lib/site-config';

export const revalidate = 900;

export default async function HilltopGatePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const feed = await getFeed();

  return (
    <HilltopExperience
      slug={id}
      steps={feed.steps}
      destination={DESTINATION}
    />
  );
}

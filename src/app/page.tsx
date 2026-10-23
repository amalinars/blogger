import { GateExperience } from '@/components/gate-experience';
import { getFeed } from '@/lib/feed';
import { DESTINATION } from '@/lib/site-config';

export const revalidate = 900;

export default async function HomePage() {
  const feed = await getFeed();

  return <GateExperience steps={feed.steps} destination={DESTINATION} />;
}

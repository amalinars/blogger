import { redirect } from 'next/navigation';

export default async function LegacyPostPage({
  params,
  searchParams
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ step?: string }>;
}) {
  const { slug } = await params;
  const { step } = await searchParams;
  const targetStep = step ? `?step=${step}` : '';
  redirect(`/read/${slug}${targetStep}`);
}

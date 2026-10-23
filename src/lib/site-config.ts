import type { SiteDestination } from './types';

export const SITE = {
  name: 'Gateway',
  title: 'Gateway to your order page',
  description:
    'Three quick steps before you are redirected to the order page. No login, no cost, clear destination.',
} as const;

export const STEP_DEFINITIONS = [
  {
    id: 'confirm',
    category: 'teknologi',
    categoryLabel: 'Technology',
    title: 'Confirm the link',
    description:
      'We make sure this session is active before opening the route to the order page.',
  },
  {
    id: 'verify',
    category: 'science',
    categoryLabel: 'Science',
    title: 'Check the destination',
    description:
      'Make sure the destination domain matches what you expect before you continue.',
  },
  {
    id: 'handoff',
    category: 'gaya-hidup',
    categoryLabel: 'Lifestyle',
    title: 'Continue to your order',
    description:
      'The final step. After this, you will be redirected to the order page.',
  },
] as const;

const DEFAULT_DESTINATION = 'https://net.riztama.my.id/orders';

function resolveDestination(): SiteDestination {
  const raw = process.env.SHORTLINK_DESTINATION_URL?.trim() || DEFAULT_DESTINATION;

  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      throw new Error('Unsupported protocol');
    }

    return {
      url: parsed.toString(),
      host: parsed.host,
      path: parsed.pathname === '/' ? '/' : parsed.pathname,
    };
  } catch {
    const fallback = new URL(DEFAULT_DESTINATION);
    return {
      url: fallback.toString(),
      host: fallback.host,
      path: fallback.pathname,
    };
  }
}

function resolveStepDelays(): number[] {
  const fallback = [8, 10, 8];
  const raw = process.env.SHORTLINK_STEP_DELAYS?.trim();
  if (!raw) return fallback;

  const values = raw.split(',').map((value) => Number(value.trim()));
  const valid =
    values.length === STEP_DEFINITIONS.length &&
    values.every((value) => Number.isFinite(value) && value >= 3 && value <= 60);

  return valid ? values : fallback;
}

export const DESTINATION = resolveDestination();
export const STEP_DELAYS = resolveStepDelays();

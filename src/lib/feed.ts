import { STEP_DEFINITIONS, STEP_DELAYS } from './site-config';
import type { ArticleFeedItem, FeedResult, GateStepData } from './types';

const FEED_BASE =
  process.env.NEWS_FEED_BASE?.replace(/\/$/, '') ||
  'https://www.theguardian.com';
const NEWS_SOURCE = 'The Guardian';
const FETCH_TIMEOUT_MS = 4000;
const CACHE_SECONDS = 900;

const FEED_PATHS: Record<string, string> = {
  teknologi: '/uk/technology/rss',
  science: '/science/rss',
  'gaya-hidup': '/lifeandstyle/rss',
};

const BLOCKED_WORDS = [
  'killed',
  'killing',
  'dead',
  'death',
  'died',
  'dies',
  'murder',
  'shooting',
  'shooter',
  'war',
  'bomb',
  'bombing',
  'crash',
  'disaster',
  'flood',
  'wildfire',
  'abuse',
  'assault',
  'rape',
  'suicide',
  'corruption',
  'fraud',
  'layoff',
  'layoffs',
  'redundancies',
  'outbreak',
  'pandemic',
  'virus',
  'cancer',
  'porn',
  'nude',
  'naked',
  'vaccine',
  'plague',
  'epidemic',
  'podcast',
  'obituary',
  'editorial',
  'opinion',
  'video',
  'protest',
  'protests',
  'minister',
  'ministers',
  'government',
  'labour',
  'coalition',
  'election',
  'elections',
  'brexit',
  'trump',
  'putin',
  'zelensky',
  'ukraine',
  'gaza',
  'israel',
  'military',
  'defence',
  'defense',
  'arms',
  'weapons',
  'missile',
  'nato',
  'summit',
  'policy',
  'regulation',
  'regulator',
  'tax',
  'taxes',
  'budget',
  'inflation',
  'retail sales',
  'jobs',
  'job',
  'cuts',
  'strike',
  'union',
  'immigration',
  'asylum',
  'refugee',
  'datacentre',
  'datacenter',
  'data centre',
  'data center',
  'illegally',
  'unemployment',
  'midterm',
  'midterms',
  'fight',
  'alcohol',
  'accused',
  'oligarch',
  'puzzle',
  'puzzles',
  'riddle',
  'quiz',
  'crossword',
  'sudoku',
  'exploit',
  'hacked',
  'hacker',
  'hackers',
  'malware',
  'breach',
  'alleged',
  'billionaire',
  'billionaires',
];

const BLOCKED_PATTERN = new RegExp(
  `\\b(?:${BLOCKED_WORDS.map((word) =>
    word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
  ).join('|')})\\b`,
  'i',
);

type FeedEntry = {
  title: string;
  description: string;
  pubDate: string;
  imageUrl: string | null;
};

type FallbackSeed = {
  title: string;
  snippet: string;
};

type FallbackSet = {
  primary: FallbackSeed;
  related: FallbackSeed[];
};

const FALLBACK_CONTENT: Record<string, FallbackSet> = {
  teknologi: {
    primary: {
      title: 'A good link keeps its context intact',
      snippet:
        'A link is more than a door. It carries context, intent, and the expectations of the person who clicks it. That is why every handoff should have a clear, checkable destination.',
    },
    related: [
      {
        title: 'Why the destination should be visible before the click',
        snippet:
          'A readable address gives the reader room to decide whether the destination is really the one they are looking for.',
      },
      {
        title: 'A short pause, a calmer decision',
        snippet:
          'A small pause is often enough to double-check the destination without changing the original intent.',
      },
    ],
  },
  science: {
    primary: {
      title: 'A short pause helps you notice the details',
      snippet:
        'A pause between two actions gives you room to check the address, the path, and the purpose of the page ahead. Small observations often prevent bigger detours.',
    },
    related: [
      {
        title: 'Why a clear destination matters',
        snippet:
          'A clear destination makes it easier to decide whether the next step is the one you actually intended to take.',
      },
      {
        title: 'Reading one thing at a time',
        snippet:
          'A single focused read can be more useful than a dozen open tabs competing for your attention.',
      },
    ],
  },
  'gaya-hidup': {
    primary: {
      title: 'One short read before you move on',
      snippet:
        'Not every journey needs to be rushed. A short article in the middle of a step can be enough to refocus on the destination ahead.',
    },
    related: [
      {
        title: 'The space between two decisions',
        snippet:
          'A deliberate pause gives you a chance to make sure the next step is really ready.',
      },
      {
        title: 'A short reading habit that still helps',
        snippet:
          'A few well-chosen paragraphs are often more useful than a lot of information you never get to digest.',
      },
    ],
  },
};

function getTag(block: string, tag: string): string {
  const match = block.match(
    new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`, 'i'),
  );
  return match?.[1] ?? '';
}

function decodeEntities(value: string): string {
  return value
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code: string) =>
      String.fromCharCode(parseInt(code, 16)),
    )
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&mdash;/g, '—')
    .replace(/&ndash;/g, '–')
    .replace(/&hellip;/g, '...');
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;

  const cut = value.slice(0, maxLength);
  const lastSpace = cut.lastIndexOf(' ');
  const cleanCut = lastSpace > 35 ? cut.slice(0, lastSpace) : cut;
  return `${cleanCut.trim()}...`;
}

function cleanText(value: unknown, maxLength = 0): string {
  if (typeof value !== 'string') return '';

  const text = decodeEntities(value)
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return maxLength > 0 ? truncate(text, maxLength) : text;
}

function stripReadMore(value: string): string {
  return value
    .replace(/\s*Continue reading(?:\.{3}|…)?\s*$/i, '')
    .trim();
}

function sanitizeImageUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;

  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function extractImage(block: string): string | null {
  const candidates: Array<{ url: string; width: number }> = [];
  const matches = block.matchAll(/<media:content\b[^>]*>/gi);

  for (const match of matches) {
    const tag = match[0];
    const urlMatch = tag.match(/\burl="([^"]+)"/i);
    if (!urlMatch) continue;

    const widthMatch = tag.match(/\bwidth="(\d+)"/i);
    candidates.push({
      url: decodeEntities(urlMatch[1]),
      width: widthMatch ? Number(widthMatch[1]) : 0,
    });
  }

  candidates.sort((left, right) => right.width - left.width);

  for (const candidate of candidates) {
    const safe = sanitizeImageUrl(candidate.url);
    if (safe) return safe;
  }

  const thumbnail = block.match(/<media:thumbnail\b[^>]*\burl="([^"]+)"/i);
  return thumbnail ? sanitizeImageUrl(decodeEntities(thumbnail[1])) : null;
}

function formatPublished(dateValue: string): string | null {
  if (!dateValue) return null;

  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return null;

  try {
    const formatted = new Intl.DateTimeFormat('en-GB', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'UTC',
    }).format(parsed);

    return `${formatted} UTC`;
  } catch {
    return null;
  }
}

function isSafeHeadline(title: string, snippet: string): boolean {
  return !BLOCKED_PATTERN.test(`${title} ${snippet}`);
}

function parseRss(xml: string): FeedEntry[] {
  const entries: FeedEntry[] = [];
  const matches = xml.matchAll(/<item\b[^>]*>([\s\S]*?)<\/item>/gi);

  for (const match of matches) {
    const block = match[1];
    const title = cleanText(getTag(block, 'title'));
    const description = stripReadMore(
      cleanText(getTag(block, 'description')),
    );

    if (!title || !description) continue;

    entries.push({
      title,
      description,
      pubDate: cleanText(getTag(block, 'pubDate')),
      imageUrl: extractImage(block),
    });
  }

  return entries;
}

function toArticle(
  item: FeedEntry,
  category: string,
  categoryLabel: string,
  id: string,
): ArticleFeedItem | null {
  const title = cleanText(item.title);
  const snippet = cleanText(item.description, 260);

  if (!title || !snippet) return null;

  return {
    id,
    category,
    categoryLabel,
    title,
    snippet,
    imageUrl: item.imageUrl,
    source: NEWS_SOURCE,
    publishedLabel: formatPublished(item.pubDate),
  };
}

function pickLiveArticles(
  rawItems: FeedEntry[],
  category: string,
  categoryLabel: string,
  seed: number,
): Pick<GateStepData, 'article' | 'related'> | null {
  const safeItems = rawItems
    .map((item, index) =>
      toArticle(item, category, categoryLabel, `${category}-${seed}-${index}`),
    )
    .filter((item): item is ArticleFeedItem => item !== null)
    .filter((item) => isSafeHeadline(item.title, item.snippet));

  if (safeItems.length === 0) return null;

  const windowSize = Math.min(12, safeItems.length);
  const start = Math.abs(seed) % windowSize;
  const article = safeItems[start];
  const related: ArticleFeedItem[] = [];

  for (let offset = 1; offset < safeItems.length && related.length < 2; offset += 1) {
    const candidate = safeItems[(start + offset) % safeItems.length];
    if (candidate.title !== article.title) related.push(candidate);
  }

  return { article, related };
}

async function fetchCategory(category: string): Promise<FeedEntry[]> {
  const path = FEED_PATHS[category];
  if (!path) return [];

  const response = await fetch(`${FEED_BASE}${path}`, {
    headers: {
      Accept: 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8',
    },
    next: { revalidate: CACHE_SECONDS },
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`News feed returned ${response.status}`);
  }

  return parseRss(await response.text());
}

function createFallback(
  category: string,
  categoryLabel: string,
): Pick<GateStepData, 'article' | 'related'> {
  const content = FALLBACK_CONTENT[category] ?? FALLBACK_CONTENT.teknologi;

  const buildArticle = (
    seed: FallbackSeed,
    key: string,
    imageSeed: string,
  ): ArticleFeedItem => ({
    id: `fallback-${category}-${key}`,
    category,
    categoryLabel,
    title: seed.title,
    snippet: seed.snippet,
    imageUrl: `https://picsum.photos/seed/${encodeURIComponent(imageSeed)}/1200/760`,
    source: 'Gateway',
    publishedLabel: null,
  });

  return {
    article: buildArticle(content.primary, 'primary', `gateway-${category}`),
    related: content.related.map((item, index) =>
      buildArticle(item, `related-${index}`, `gateway-${category}-${index}`),
    ),
  };
}

export async function getFeed(): Promise<FeedResult> {
  const seed = Math.floor(Date.now() / (CACHE_SECONDS * 1000));
  const settled = await Promise.allSettled(
    STEP_DEFINITIONS.map((definition) => fetchCategory(definition.category)),
  );

  let liveCount = 0;

  const steps: GateStepData[] = STEP_DEFINITIONS.map((definition, index) => {
    const result = settled[index];
    const live =
      result.status === 'fulfilled'
        ? pickLiveArticles(
            result.value,
            definition.category,
            definition.categoryLabel,
            seed + index * 7,
          )
        : null;

    if (live) liveCount += 1;

    const content = live ?? createFallback(definition.category, definition.categoryLabel);

    return {
      id: definition.id,
      index,
      title: definition.title,
      description: definition.description,
      delaySeconds: STEP_DELAYS[index],
      ...content,
    };
  });

  return {
    source: liveCount === STEP_DEFINITIONS.length ? 'live' : 'fallback',
    fetchedAt: new Date().toISOString(),
    steps,
  };
}

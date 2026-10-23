export type ArticleFeedItem = {
  id: string;
  category: string;
  categoryLabel: string;
  title: string;
  snippet: string;
  imageUrl: string | null;
  source: string;
  publishedLabel: string | null;
};

export type GateStepData = {
  id: string;
  index: number;
  title: string;
  description: string;
  delaySeconds: number;
  article: ArticleFeedItem;
  related: ArticleFeedItem[];
};

export type FeedResult = {
  source: 'live' | 'fallback';
  fetchedAt: string;
  steps: GateStepData[];
};

export type SiteDestination = {
  url: string;
  host: string;
  path: string;
};

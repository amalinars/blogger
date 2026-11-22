export interface WorkerState {
  worker_id: number;
  status: "IDLE" | "RUNNING" | "PASS" | "FAIL" | string;
  step_key: string;
  step_label: string;
  activity: string;
  proxy_ip: string;
  country: string;
  country_flag: string;
  target_url?: string;
  sessions_done: number;
  sessions_failed: number;
  impressions: number;
  last_duration_s: number | null;
  last_error: string | null;
  last_activity_ts: number;
}

export interface ImpressionsBreakdown {
  vignette?: number;
  popunder?: number;
  direct_link?: number;
  banner?: number;
  in_page_push?: number;
  video_slider?: number;
}

export interface NodeStats {
  total_sessions?: number;
  passed?: number;
  failed?: number;
  pass_rate_pct?: number;
  impressions_expected?: number;
  impressions_breakdown?: ImpressionsBreakdown;
  sessions_per_hour?: number;
  impressions_per_hour?: number;
  uptime_seconds?: number;
}

export interface NodeMeta {
  hostname?: string;
  os?: string;
  cpu_count?: number;
  chain?: boolean;
  potato?: boolean;
  headless?: boolean;
}

export interface BotNode {
  node_name: string;
  target_network: string;
  target_url: string;
  status: "RUNNING" | "STOPPED" | string;
  workers_count: number;
  workers_state: WorkerState[];
  stats: NodeStats;
  meta: NodeMeta;
  started_at: string;
  last_heartbeat: string;
  updated_at: string;
}

export type HealthState = "ONLINE" | "LAGGING" | "OFFLINE" | "STOPPED";

export interface StepDef {
  key: string;
  label: string;
}

export const MONETAG_STEPS: StepDef[] = [
  { key: "proxy", label: "Proxy" },
  { key: "open_web", label: "Web" },
  { key: "vignette", label: "Vignette" },
  { key: "popunder", label: "Popunder" },
  { key: "direct_link", label: "Direct" },
  { key: "done", label: "Selesai" },
];

export const ARTIKLE_STEPS: StepDef[] = [
  { key: "proxy", label: "Proxy" },
  { key: "open_web", label: "Web" },
  { key: "banner_push", label: "Banner" },
  { key: "article_1", label: "Art #1" },
  { key: "article_2", label: "Art #2" },
  { key: "done", label: "Selesai" },
];

export function getStepsForTarget(targetNetwork: string): StepDef[] {
  return targetNetwork.toUpperCase().includes("ARTIKLE")
    ? ARTIKLE_STEPS
    : MONETAG_STEPS;
}

export function computeNodeHealth(node: BotNode, nowMs: number): {
  health: HealthState;
  ageSeconds: number;
} {
  const hbMs = Date.parse(node.last_heartbeat || "");
  const ageSeconds = Number.isFinite(hbMs)
    ? Math.max(0, Math.floor((nowMs - hbMs) / 1000))
    : 999999;

  if (String(node.status).toUpperCase() === "STOPPED") {
    return { health: "STOPPED", ageSeconds };
  }
  if (ageSeconds <= 20) {
    return { health: "ONLINE", ageSeconds };
  }
  if (ageSeconds <= 45) {
    return { health: "LAGGING", ageSeconds };
  }
  return { health: "OFFLINE", ageSeconds };
}

export function formatRelativeAge(seconds: number): string {
  if (seconds < 5) return "baru saja";
  if (seconds < 60) return `${seconds}d lalu`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m lalu`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}j ${mins % 60}m lalu`;
  const days = Math.floor(hours / 24);
  return `${days}h ${hours % 24}j lalu`;
}

export function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}j ${m}m`;
  if (m > 0) return `${m}m ${s % 60}d`;
  return `${s}d`;
}

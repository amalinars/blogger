import { useState } from "react";
import {
  Activity,
  AlertOctagon,
  ChevronDown,
  ChevronUp,
  Cpu,
  ExternalLink,
  RotateCcw,
  Server,
  Sparkles,
  Trash2,
  WifiOff,
} from "lucide-react";
import {
  BotNode,
  computeNodeHealth,
  formatRelativeAge,
  formatUptime,
} from "../types";
import { WorkerCard } from "./WorkerCard";

interface ServerPanelProps {
  node: BotNode;
  nowMs: number;
  onResetStats: (nodeName: string) => Promise<void>;
  onDeleteNode: (nodeName: string) => Promise<void>;
}

const BREAKDOWN_LABELS: Array<{ key: keyof NonNullable<BotNode["stats"]["impressions_breakdown"]>; label: string }> = [
  { key: "vignette", label: "Vignette" },
  { key: "popunder", label: "Popunder" },
  { key: "direct_link", label: "Direct Link" },
  { key: "banner", label: "Banner" },
  { key: "in_page_push", label: "Push" },
  { key: "video_slider", label: "Video" },
];

export function ServerPanel({
  node,
  nowMs,
  onResetStats,
  onDeleteNode,
}: ServerPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const { health, ageSeconds } = computeNodeHealth(node, nowMs);
  const isAlive = health === "ONLINE" || health === "LAGGING";

  const stats = node.stats || {};
  const breakdown = stats.impressions_breakdown || {};
  const workers = Array.isArray(node.workers_state) ? node.workers_state : [];
  const activeWorkers = isAlive
    ? workers.filter((w) => w.status === "RUNNING" || w.status === "PASS").length
    : 0;

  const healthMeta = {
    ONLINE: {
      border: "border-emerald-500/30",
      bg: "bg-slate-900/65",
      pill: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
      dot: "bg-emerald-400 animate-pulse",
      label: "ONLINE",
    },
    LAGGING: {
      border: "border-amber-500/45",
      bg: "bg-amber-950/10",
      pill: "bg-amber-500/15 text-amber-300 border-amber-500/40",
      dot: "bg-amber-400 animate-pulse",
      label: "LAGGING",
    },
    OFFLINE: {
      border: "border-rose-500/60 shadow-[0_0_24px_-8px_rgba(244,63,94,0.45)]",
      bg: "bg-rose-950/15",
      pill: "bg-rose-500/20 text-rose-200 border-rose-500/50",
      dot: "bg-rose-500",
      label: "OFFLINE / DISCONNECT",
    },
    STOPPED: {
      border: "border-slate-800",
      bg: "bg-slate-900/40",
      pill: "bg-slate-800 text-slate-400 border-slate-700",
      dot: "bg-slate-500",
      label: "STOPPED",
    },
  }[health];

  const handleReset = async () => {
    setBusy(true);
    try {
      await onResetStats(node.node_name);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 4000);
      return;
    }
    setBusy(true);
    try {
      await onDeleteNode(node.node_name);
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  const breakdownEntries = BREAKDOWN_LABELS.filter(
    ({ key }) => Number(breakdown[key] || 0) > 0
  );

  return (
    <section
      className={`rounded-2xl border overflow-hidden transition-all ${healthMeta.border} ${healthMeta.bg}`}
    >
      {/* Server Header */}
      <div className="p-4 sm:p-5 border-b border-slate-800/80 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div
              className={`p-2.5 rounded-xl border shrink-0 ${
                health === "OFFLINE"
                  ? "bg-rose-500/15 border-rose-500/40 text-rose-300"
                  : isAlive
                    ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
                    : "bg-slate-800 border-slate-700 text-slate-400"
              }`}
            >
              {health === "OFFLINE" ? (
                <WifiOff className="w-5 h-5" />
              ) : (
                <Server className="w-5 h-5" />
              )}
            </div>

            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base sm:text-lg font-bold text-white tracking-tight truncate">
                  {node.node_name}
                </h2>
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${healthMeta.pill}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${healthMeta.dot}`} />
                  {healthMeta.label} · {formatRelativeAge(ageSeconds)}
                </span>
                <span
                  className={`px-2 py-0.5 rounded-md text-[11px] font-mono font-semibold border ${
                    node.target_network.includes("ARTIKLE")
                      ? "bg-violet-500/15 text-violet-300 border-violet-500/30"
                      : "bg-blue-500/15 text-blue-300 border-blue-500/30"
                  }`}
                >
                  {node.target_network}
                </span>
              </div>

              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                {node.target_url && (
                  <span className="inline-flex items-center gap-1 truncate max-w-[260px]">
                    <ExternalLink className="w-3 h-3 shrink-0 text-slate-500" />
                    {node.target_url.replace(/^https?:\/\//, "")}
                  </span>
                )}
                {node.meta?.cpu_count && (
                  <span className="inline-flex items-center gap-1">
                    <Cpu className="w-3 h-3 text-slate-500" />
                    {node.meta.cpu_count} Core
                  </span>
                )}
                <span>
                  Mode: {node.meta?.chain === false ? "Direct Proxy" : "Chain"}
                </span>
                {isAlive && stats.uptime_seconds != null && (
                  <span>Uptime: {formatUptime(stats.uptime_seconds)}</span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleReset}
              disabled={busy || isAlive}
              title={
                isAlive
                  ? "Stop server dulu sebelum reset statistik"
                  : "Reset statistik server ini ke 0"
              }
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Reset</span>
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={busy}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                confirmDelete
                  ? "bg-rose-600 border-rose-500 text-white"
                  : "border-slate-700 bg-slate-800/80 text-slate-300 hover:border-rose-500/50 hover:text-rose-300"
              }`}
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>{confirmDelete ? "Konfirmasi Hapus?" : "Hapus"}</span>
            </button>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="p-1.5 rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700"
              aria-label="Toggle workers"
            >
              {expanded ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* Crash Notice inside Offline Server */}
        {health === "OFFLINE" && (
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-rose-500/15 border border-rose-500/35 text-xs text-rose-200">
            <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
            <span>
              Heartbeat terputus <strong>{formatRelativeAge(ageSeconds)}</strong> tanpa stop normal — kemungkinan Google Colab disconnect / runtime habis / proses crash.
            </span>
          </div>
        )}

        {/* Server KPI Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="rounded-xl bg-slate-950/60 border border-slate-800/80 px-3.5 py-2.5">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              Worker
            </div>
            <div className="mt-1 text-lg font-bold text-white">
              {activeWorkers}
              <span className="text-xs font-normal text-slate-500">
                {" "}
                / {node.workers_count || workers.length} aktif
              </span>
            </div>
          </div>

          <div className="rounded-xl bg-slate-950/60 border border-slate-800/80 px-3.5 py-2.5">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              Expected Impressions
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-lg font-bold text-amber-300">
                {(stats.impressions_expected || 0).toLocaleString("id-ID")}
              </span>
              {isAlive && (stats.impressions_per_hour || 0) > 0 && (
                <span className="text-[11px] text-slate-400 font-mono">
                  ~{Math.round(stats.impressions_per_hour || 0)}/jam
                </span>
              )}
            </div>
          </div>

          <div className="rounded-xl bg-slate-950/60 border border-slate-800/80 px-3.5 py-2.5">
            <div className="text-[11px] text-slate-400">Sesi (Lolos / Gagal)</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-lg font-bold text-emerald-400">
                {(stats.passed || 0).toLocaleString("id-ID")}
              </span>
              <span className="text-xs text-rose-400 font-semibold">
                / {(stats.failed || 0).toLocaleString("id-ID")}
              </span>
              <span className="text-[11px] text-slate-500">
                ({stats.pass_rate_pct ?? 0}%)
              </span>
            </div>
          </div>

          <div className="rounded-xl bg-slate-950/60 border border-slate-800/80 px-3.5 py-2.5">
            <div className="text-[11px] text-slate-400">Rincian Format Iklan</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {breakdownEntries.length > 0 ? (
                breakdownEntries.map(({ key, label }) => (
                  <span
                    key={key}
                    className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700/80 text-[10px] text-slate-200 font-mono"
                  >
                    {label}: {breakdown[key]}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">Belum ada impresi</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Worker Cards Area */}
      {expanded && (
        <div className="p-4 sm:p-5">
          {workers.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {workers.map((w) => (
                <WorkerCard
                  key={w.worker_id}
                  worker={w}
                  targetNetwork={node.target_network}
                  serverAlive={isAlive}
                  nowMs={nowMs}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-xs text-slate-500">
              Belum ada data worker yang dilaporkan.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

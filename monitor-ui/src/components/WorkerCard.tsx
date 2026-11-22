import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Globe,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import { getStepsForTarget, WorkerState } from "../types";

interface WorkerCardProps {
  worker: WorkerState;
  targetNetwork: string;
  serverAlive: boolean;
  nowMs: number;
}

export function WorkerCard({
  worker,
  targetNetwork,
  serverAlive,
  nowMs,
}: WorkerCardProps) {
  const steps = getStepsForTarget(targetNetwork);
  const isFailed = worker.step_key === "failed" || worker.status === "FAIL";
  const isDone = worker.step_key === "done" || worker.status === "PASS";

  let activeIdx = steps.findIndex((s) => s.key === worker.step_key);
  if (activeIdx === -1) {
    activeIdx = isDone ? steps.length - 1 : 0;
  }

  const idleSec = worker.last_activity_ts
    ? Math.max(0, Math.floor(nowMs / 1000) - worker.last_activity_ts)
    : 0;
  const isStuck = serverAlive && worker.status === "RUNNING" && idleSec > 120;

  const progressPct = isFailed
    ? 100
    : Math.round(((activeIdx + 1) / steps.length) * 100);

  const badge = !serverAlive
    ? {
        cls: "bg-slate-800 text-slate-400 border-slate-700",
        label: "Terhenti",
        icon: <Clock className="w-3 h-3" />,
      }
    : isStuck
      ? {
          cls: "bg-amber-500/15 text-amber-300 border-amber-500/40",
          label: `Macet ${Math.floor(idleSec / 60)}m`,
          icon: <AlertTriangle className="w-3 h-3" />,
        }
      : isFailed
        ? {
            cls: "bg-rose-500/15 text-rose-300 border-rose-500/40",
            label: "Gagal",
            icon: <XCircle className="w-3 h-3" />,
          }
        : isDone
          ? {
              cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
              label: "Lolos",
              icon: <CheckCircle2 className="w-3 h-3" />,
            }
          : {
              cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40",
              label: worker.step_label || "Berjalan",
              icon: <Loader2 className="w-3 h-3 animate-spin" />,
            };

  return (
    <div
      className={`rounded-xl border p-3.5 transition-colors flex flex-col justify-between gap-3 ${
        !serverAlive
          ? "bg-slate-900/40 border-slate-800/80 opacity-75"
          : isStuck
            ? "bg-amber-950/15 border-amber-500/40"
            : isFailed
              ? "bg-rose-950/15 border-rose-500/30"
              : "bg-slate-900/75 border-slate-800 hover:border-slate-700"
      }`}
    >
      {/* Header Worker */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 font-mono text-xs font-bold text-slate-200 shrink-0">
            W{worker.worker_id}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-xs font-medium text-slate-200 truncate">
              <span>{worker.country_flag || "🌐"}</span>
              <span className="truncate font-mono text-[11px] text-slate-300">
                {worker.proxy_ip && worker.proxy_ip !== "—"
                  ? worker.proxy_ip
                  : "Mencari IP..."}
              </span>
            </div>
            <div className="text-[11px] text-slate-500 truncate flex items-center gap-1">
              <Globe className="w-2.5 h-2.5 shrink-0" />
              <span>{worker.country || "—"}</span>
            </div>
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border shrink-0 ${badge.cls}`}
        >
          {badge.icon}
          <span className="max-w-[92px] truncate">{badge.label}</span>
        </span>
      </div>

      {/* Visual Stepper Progress */}
      <div className="space-y-1.5">
        <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              !serverAlive
                ? "bg-slate-600"
                : isFailed
                  ? "bg-rose-500"
                  : isDone
                    ? "bg-emerald-400"
                    : isStuck
                      ? "bg-amber-400"
                      : "bg-gradient-to-r from-cyan-400 to-blue-500"
            }`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="grid grid-cols-6 gap-1">
          {steps.map((s, idx) => {
            const passed = !isFailed && idx < activeIdx;
            const current = !isFailed && idx === activeIdx;
            return (
              <span
                key={s.key}
                className={`text-[10px] text-center truncate ${
                  current
                    ? "text-cyan-300 font-semibold"
                    : passed
                      ? "text-emerald-400/80"
                      : "text-slate-600"
                }`}
              >
                {s.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Current Action (Translated from Flow State, Not Raw Logs) */}
      <div
        className={`text-xs px-2.5 py-1.5 rounded-lg border truncate ${
          isFailed
            ? "bg-rose-950/30 border-rose-900/50 text-rose-200"
            : "bg-slate-950/60 border-slate-800/80 text-slate-300"
        }`}
        title={worker.activity}
      >
        {worker.activity || "Menunggu tugas..."}
      </div>

      {/* Worker Mini Counters */}
      <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-800/80">
        <div className="flex items-center gap-3">
          <span className="text-emerald-400 font-semibold">
            {worker.sessions_done || 0}{" "}
            <span className="text-slate-500 font-normal">lolos</span>
          </span>
          <span className="text-rose-400 font-semibold">
            {worker.sessions_failed || 0}{" "}
            <span className="text-slate-500 font-normal">gagal</span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-slate-400">
          <span className="inline-flex items-center gap-1 text-amber-300 font-semibold">
            <Sparkles className="w-3 h-3" />
            {worker.impressions || 0}
          </span>
          {worker.last_duration_s != null && (
            <span className="font-mono text-[10px] text-slate-500">
              {worker.last_duration_s}s
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

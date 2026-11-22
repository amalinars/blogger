import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Radio,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  Terminal,
} from "lucide-react";
import { supabase } from "./lib/supabase";
import { BotNode, computeNodeHealth, formatRelativeAge, HealthState } from "./types";
import { ServerPanel } from "./components/ServerPanel";

type FilterMode = "ALL" | HealthState;

const HEALTH_SORT_ORDER: Record<HealthState, number> = {
  OFFLINE: 0,
  LAGGING: 1,
  ONLINE: 2,
  STOPPED: 3,
};

export function App() {
  const [nodes, setNodes] = useState<BotNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [rtStatus, setRtStatus] = useState<"connecting" | "connected" | "fallback">("connecting");
  const [filter, setFilter] = useState<FilterMode>("ALL");
  const [query, setQuery] = useState("");
  const [nowMs, setNowMs] = useState(() => Date.now());

  const fetchNodes = useCallback(async () => {
    const { data, error } = await supabase
      .from("bot_nodes")
      .select("*")
      .order("last_heartbeat", { ascending: false });

    if (error) {
      setErrorMsg(error.message);
    } else {
      setErrorMsg(null);
      setNodes((data as BotNode[]) || []);
    }
    setLoading(false);
  }, []);

  // 1s live clock tick so Health Ping badges & OFFLINE transitions update smoothly
  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Initial fetch + Supabase Realtime postgres_changes + 10s fallback sync
  useEffect(() => {
    fetchNodes();

    const channel = supabase
      .channel("bot-nodes-realtime")
      .on(
        "postgres_changes",
        { event: "*", schema: "proxxies", table: "bot_nodes" },
        (payload) => {
          if (payload.eventType === "DELETE") {
            const oldName = (payload.old as Partial<BotNode>)?.node_name;
            if (oldName) {
              setNodes((prev) => prev.filter((n) => n.node_name !== oldName));
            }
            return;
          }
          const incoming = payload.new as BotNode;
          if (!incoming?.node_name) return;
          setNodes((prev) => {
            const idx = prev.findIndex((n) => n.node_name === incoming.node_name);
            if (idx === -1) return [incoming, ...prev];
            const next = [...prev];
            next[idx] = incoming;
            return next;
          });
        }
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") {
          setRtStatus("connected");
        } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
          setRtStatus("fallback");
        }
      });

    // Fallback sync ringan setiap 10s jika WebSocket sempat terputus
    const poll = setInterval(fetchNodes, 10000);

    return () => {
      clearInterval(poll);
      supabase.removeChannel(channel);
    };
  }, [fetchNodes]);

  const handleResetStats = async (nodeName: string) => {
    const emptyStats = {
      total_sessions: 0,
      passed: 0,
      failed: 0,
      pass_rate_pct: 0,
      impressions_expected: 0,
      impressions_breakdown: {
        vignette: 0,
        popunder: 0,
        direct_link: 0,
        banner: 0,
        in_page_push: 0,
        video_slider: 0,
      },
      sessions_per_hour: 0,
      impressions_per_hour: 0,
      uptime_seconds: 0,
    };
    const { error } = await supabase
      .from("bot_nodes")
      .update({ stats: emptyStats, updated_at: new Date().toISOString() })
      .eq("node_name", nodeName);
    if (!error) {
      setNodes((prev) =>
        prev.map((n) => (n.node_name === nodeName ? { ...n, stats: emptyStats } : n))
      );
    }
  };

  const handleDeleteNode = async (nodeName: string) => {
    const { error } = await supabase
      .from("bot_nodes")
      .delete()
      .eq("node_name", nodeName);
    if (!error) {
      setNodes((prev) => prev.filter((n) => n.node_name !== nodeName));
    }
  };

  const enriched = useMemo(() => {
    return nodes
      .map((node) => ({
        node,
        ...computeNodeHealth(node, nowMs),
      }))
      .sort((a, b) => {
        const diff = HEALTH_SORT_ORDER[a.health] - HEALTH_SORT_ORDER[b.health];
        if (diff !== 0) return diff;
        return a.node.node_name.localeCompare(b.node.node_name);
      });
  }, [nodes, nowMs]);

  const summary = useMemo(() => {
    let online = 0;
    let lagging = 0;
    let offline = 0;
    let stopped = 0;
    let activeWorkers = 0;
    let totalWorkers = 0;
    let totalImpressions = 0;
    let totalImpPerHour = 0;
    let totalPassed = 0;
    let totalFailed = 0;

    for (const item of enriched) {
      if (item.health === "ONLINE") online++;
      else if (item.health === "LAGGING") lagging++;
      else if (item.health === "OFFLINE") offline++;
      else stopped++;

      const wCount = item.node.workers_count || item.node.workers_state?.length || 0;
      totalWorkers += wCount;
      if (item.health === "ONLINE" || item.health === "LAGGING") {
        activeWorkers += wCount;
        totalImpPerHour += Number(item.node.stats?.impressions_per_hour || 0);
      }

      totalImpressions += Number(item.node.stats?.impressions_expected || 0);
      totalPassed += Number(item.node.stats?.passed || 0);
      totalFailed += Number(item.node.stats?.failed || 0);
    }

    const totalSessions = totalPassed + totalFailed;
    const passRate =
      totalSessions > 0 ? Math.round((totalPassed / totalSessions) * 1000) / 10 : 0;

    return {
      online,
      lagging,
      offline,
      stopped,
      activeWorkers,
      totalWorkers,
      totalImpressions,
      totalImpPerHour: Math.round(totalImpPerHour),
      totalPassed,
      totalFailed,
      passRate,
    };
  }, [enriched]);

  const offlineAlerts = useMemo(
    () => enriched.filter((e) => e.health === "OFFLINE"),
    [enriched]
  );

  const visibleNodes = useMemo(() => {
    const q = query.trim().toLowerCase();
    return enriched.filter((item) => {
      if (filter !== "ALL" && item.health !== filter) return false;
      if (
        q &&
        !item.node.node_name.toLowerCase().includes(q) &&
        !item.node.target_network.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [enriched, filter, query]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Navbar */}
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Server className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white leading-tight">
                Fleet Telemetry Center
              </h1>
              <p className="text-[11px] text-slate-400">
                Realtime multi-server worker &amp; impression monitor
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                rtStatus === "connected"
                  ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                  : rtStatus === "fallback"
                    ? "bg-amber-500/10 text-amber-300 border-amber-500/30"
                    : "bg-slate-800 text-slate-300 border-slate-700"
              }`}
            >
              <Radio
                className={`w-3.5 h-3.5 ${
                  rtStatus === "connected" ? "animate-pulse" : ""
                }`}
              />
              {rtStatus === "connected"
                ? "Realtime Live"
                : rtStatus === "fallback"
                  ? "Sync 10s"
                  : "Menghubungkan..."}
            </span>
            <button
              type="button"
              onClick={fetchNodes}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 border border-slate-700 text-slate-200 hover:bg-slate-800 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Global Offline Alert Banner */}
        {offlineAlerts.length > 0 && (
          <div className="rounded-2xl border border-rose-500/50 bg-rose-950/30 p-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="text-sm font-bold text-rose-200">
                  {offlineAlerts.length} Server Terputus / Offline!
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {offlineAlerts.map(({ node, ageSeconds }) => (
                    <span
                      key={node.node_name}
                      className="px-2 py-0.5 rounded-md bg-rose-500/20 border border-rose-500/40 text-xs font-mono text-rose-100"
                    >
                      {node.node_name} ({formatRelativeAge(ageSeconds)})
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setFilter(filter === "OFFLINE" ? "ALL" : "OFFLINE")}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition-colors"
            >
              {filter === "OFFLINE" ? "Tampilkan Semua" : "Fokus Server Offline"}
            </button>
          </div>
        )}

        {/* SQL / Connection Error */}
        {errorMsg && (
          <div className="rounded-2xl border border-amber-500/40 bg-amber-950/20 p-4 text-xs text-amber-200 space-y-1">
            <div className="font-bold text-amber-300">
              Gagal membaca tabel proxxies.bot_nodes: {errorMsg}
            </div>
            <p className="text-amber-200/80">
              Pastikan file <code className="font-mono text-amber-100">setup_supabase_telemetry.sql</code> sudah dijalankan sekali di Supabase SQL Editor dan schema <code className="font-mono text-amber-100">proxxies</code> ter-expose.
            </p>
          </div>
        )}

        {/* Top Global KPI Strip */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-2xl bg-slate-900/70 border border-slate-800 p-4">
            <div className="text-xs text-slate-400 flex items-center gap-1.5">
              <Server className="w-4 h-4 text-cyan-400" />
              Armada Server
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">
                {summary.online + summary.lagging}
              </span>
              <span className="text-xs text-emerald-400 font-medium">online</span>
              {summary.offline > 0 && (
                <span className="text-xs text-rose-400 font-semibold">
                  · {summary.offline} offline
                </span>
              )}
              {summary.stopped > 0 && (
                <span className="text-xs text-slate-500">
                  · {summary.stopped} stop
                </span>
              )}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-900/70 border border-slate-800 p-4">
            <div className="text-xs text-slate-400 flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-blue-400" />
              Worker Aktif
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-white">
                {summary.activeWorkers}
              </span>
              <span className="text-xs text-slate-500">
                / {summary.totalWorkers} terdaftar
              </span>
            </div>
          </div>

          <div className="rounded-2xl bg-slate-900/70 border border-slate-800 p-4">
            <div className="text-xs text-slate-400 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-amber-400" />
              Total Expected Impressions
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-amber-300">
                {summary.totalImpressions.toLocaleString("id-ID")}
              </span>
              {summary.totalImpPerHour > 0 && (
                <span className="text-xs font-mono text-slate-400">
                  ~{summary.totalImpPerHour.toLocaleString("id-ID")}/jam
                </span>
              )}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-900/70 border border-slate-800 p-4">
            <div className="text-xs text-slate-400 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Global Pass Rate
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-bold text-emerald-400">
                {summary.passRate}%
              </span>
              <span className="text-xs text-slate-400">
                ({summary.totalPassed} lolos / {summary.totalFailed} gagal)
              </span>
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                { id: "ALL", label: `Semua (${enriched.length})` },
                { id: "ONLINE", label: `Online (${summary.online})` },
                { id: "OFFLINE", label: `Offline (${summary.offline})` },
                { id: "STOPPED", label: `Stopped (${summary.stopped})` },
              ] as Array<{ id: FilterMode; label: string }>
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  filter === tab.id
                    ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-200"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cari nama server atau target..."
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/60"
            />
          </div>
        </div>

        {/* Server Panels */}
        {loading ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-12 text-center text-sm text-slate-400">
            Memuat data server dari Supabase...
          </div>
        ) : visibleNodes.length > 0 ? (
          <div className="space-y-5">
            {visibleNodes.map(({ node }) => (
              <ServerPanel
                key={node.node_name}
                node={node}
                nowMs={nowMs}
                onResetStats={handleResetStats}
                onDeleteNode={handleDeleteNode}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-10 text-center space-y-3">
            <Terminal className="w-8 h-8 text-slate-600 mx-auto" />
            <div className="text-sm font-semibold text-slate-200">
              {enriched.length === 0
                ? "Belum ada server yang melapor ke Supabase"
                : "Tidak ada server yang cocok dengan filter"}
            </div>
            {enriched.length === 0 && (
              <div className="max-w-xl mx-auto text-xs text-slate-400 space-y-2">
                <p>Jalankan bot dengan flag <code className="text-cyan-300 font-mono">--name</code> di VPS / Google Colab agar langsung muncul persisten di sini:</p>
                <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-left font-mono text-[11px] text-cyan-200 overflow-x-auto">
                  python3 run_bot.py --target monetag -w 8 --name vps_rata_kanan
                </pre>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
export default App;

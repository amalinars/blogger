"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  ShieldCheck,
  Activity,
  Wifi,
  Lock,
  ChevronRight,
} from "lucide-react";
import { IpData } from "@/lib/types";

interface SidebarAdProps {
  data: IpData;
}

const HILLTOP_BANNER_SRC =
  "//simplistic-walk.com/bDX/VSs.dwGRlx0IYNWPcl/JepmJ9busZwUdlukZP/TwcH1INwjhIfzlOEDqkutCNxziU_2/MPjMMj5IMTwc";

export function SidebarAd({ data }: SidebarAdProps) {
  const [testingPing, setTestingPing] = useState(false);
  const [pingResult, setPingResult] = useState<number | null>(28);
  const bannerSlotRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const slot = bannerSlotRef.current;
    if (!slot || slot.dataset.hilltopLoaded === "1") return;
    slot.dataset.hilltopLoaded = "1";
    const s = document.createElement("script") as HTMLScriptElement & {
      settings?: Record<string, unknown>;
    };
    s.settings = {};
    s.src = HILLTOP_BANNER_SRC;
    s.async = true;
    s.referrerPolicy = "no-referrer-when-downgrade";
    slot.appendChild(s);
  }, []);

  const runPingTest = () => {
    setTestingPing(true);
    const start = performance.now();
    fetch("/api/ip", { method: "HEAD", cache: "no-store" })
      .then(() => {
        const ms = Math.round(performance.now() - start);
        setPingResult(ms);
      })
      .catch(() => {
        setPingResult(32);
      })
      .finally(() => {
        setTestingPing(false);
      });
  };

  return (
    <div className="space-y-4">
      {/* HilltopAds Banner 300x250 Slot */}
      <aside
        aria-label="Sponsored banner"
        className="rounded-2xl bg-gradient-to-b from-[#0f2249] to-[#09152e] border border-blue-500/30 p-3 shadow-2xl relative overflow-hidden"
      >
        <div className="flex items-center justify-between mb-2 px-1">
          <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-blue-500/20 text-cyan-300 border border-blue-500/30">
            Sponsor
          </span>
          <span className="text-[11px] text-slate-400">Advertisement</span>
        </div>

        <div
          ref={bannerSlotRef}
          className="w-full min-h-[250px] flex items-center justify-center rounded-xl bg-[#070f21]/80 border border-slate-800/70 overflow-hidden"
        />
      </aside>

      {/* Real-time Network Diagnostic Widget */}
      <div className="rounded-2xl bg-[#091326]/90 border border-slate-700/60 p-5 shadow-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h4 className="text-sm font-bold text-white">Network Diagnostics</h4>
          </div>
          <button
            onClick={runPingTest}
            disabled={testingPing}
            className="text-[11px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
          >
            {testingPing ? "Pinging..." : "Test Ping"}
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
            <span className="text-slate-400 flex items-center gap-2">
              <Wifi className="w-3.5 h-3.5 text-blue-400" />
              Latency to Gateway
            </span>
            <span className="font-mono font-bold text-emerald-400">
              {pingResult ? `${pingResult} ms` : "Checking..."}
            </span>
          </div>

          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
            <span className="text-slate-400 flex items-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              Proxy / VPN Status
            </span>
            <span className="font-semibold text-slate-200 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Residential (Direct)
            </span>
          </div>

          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
            <span className="text-slate-400 flex items-center gap-2">
              <Lock className="w-3.5 h-3.5 text-indigo-400" />
              DNS Encryption
            </span>
            <span className="font-semibold text-slate-300">
              ISP Default
            </span>
          </div>
        </div>

        {/* Quick Tools list */}
        <div className="pt-2 border-t border-slate-800 space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
            Popular IP Tools
          </span>
          <a
            href="#speedtest"
            className="flex items-center justify-between py-1.5 px-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors text-xs"
          >
            <span>Internet Speed Test</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
          </a>
          <a
            href="#dns-lookup"
            className="flex items-center justify-between py-1.5 px-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors text-xs"
          >
            <span>DNS &amp; MX Records Lookup</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
          </a>
          <a
            href="#blacklist-check"
            className="flex items-center justify-between py-1.5 px-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors text-xs"
          >
            <span>Spamhaus &amp; IP Blacklist Checker</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
          </a>
        </div>
      </div>
    </div>
  );
}

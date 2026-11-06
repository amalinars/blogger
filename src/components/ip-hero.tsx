"use client";

import React, { useState } from "react";
import { Copy, Check, RefreshCw, ShieldCheck, Share2, HelpCircle } from "lucide-react";
import { IpData } from "@/lib/types";

interface IpHeroProps {
  data: IpData;
  onRefresh: () => void;
  isRefreshing?: boolean;
}

export function IpHero({ data, onRefresh, isRefreshing = false }: IpHeroProps) {
  const [copiedV4, setCopiedV4] = useState(false);
  const [copiedV6, setCopiedV6] = useState(false);
  const [showIpv6Help, setShowIpv6Help] = useState(false);

  const copyToClipboard = (text: string, isV4: boolean) => {
    navigator.clipboard.writeText(text);
    if (isV4) {
      setCopiedV4(true);
      setTimeout(() => setCopiedV4(false), 2000);
    } else {
      setCopiedV6(true);
      setTimeout(() => setCopiedV6(false), 2000);
    }
  };

  return (
    <div className="w-full">
      {/* Title + Status bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight flex items-center gap-2">
            <span>What Is My IP?</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live Online
            </span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Real-time public IP address detection &amp; network intelligence
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 rounded-lg bg-[#0d1c3a] hover:bg-[#122854] border border-blue-500/30 text-xs font-medium text-slate-200 hover:text-white transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-60"
            title="Refresh current IP"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${isRefreshing ? "animate-spin" : ""}`} />
            <span>{isRefreshing ? "Refreshing..." : "Refresh IP"}</span>
          </button>
        </div>
      </div>

      {/* Main IP Highlight Card */}
      <div className="rounded-2xl bg-[#091326]/90 border border-slate-700/60 p-4 sm:p-6 shadow-2xl backdrop-blur-md relative overflow-hidden">
        {/* Glow ambient background */}
        <div className="absolute top-0 right-0 w-80 h-40 bg-gradient-to-bl from-cyan-500/10 to-blue-600/5 rounded-full blur-3xl pointer-events-none" />

        <div className="space-y-4 relative z-10">
          {/* IPv4 Row (Exact layout from screenshot, made modern) */}
          <div className="flex flex-col md:flex-row md:items-center justify-between p-3.5 sm:p-4 rounded-xl bg-[#0e1a35]/80 border border-cyan-500/20 hover:border-cyan-500/40 transition-all gap-3">
            <div className="flex flex-wrap items-baseline gap-2 sm:gap-4">
              <span className="text-sm font-semibold text-slate-300">
                Your IP Address (IPv4)
              </span>
              <span className="font-mono text-xl sm:text-3xl font-bold text-cyan-400 tracking-wide select-all glow-ip">
                {data.ip}
              </span>
            </div>

            <div className="flex items-center gap-2 shrink-0 self-start md:self-center">
              <button
                onClick={() => copyToClipboard(data.ip, true)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md ${
                  copiedV4
                    ? "bg-emerald-600 text-white shadow-emerald-900/30"
                    : "bg-cyan-600 hover:bg-cyan-500 text-white shadow-cyan-900/30 active:scale-95"
                }`}
              >
                {copiedV4 ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>

              <button
                onClick={() => {
                  if (navigator.share) {
                    navigator.share({
                      title: "My IP Address",
                      text: `My public IP is ${data.ip}`,
                    });
                  } else {
                    copyToClipboard(data.ip, true);
                  }
                }}
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                title="Share IP"
              >
                <Share2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* IPv6 Row */}
          <div className="flex flex-col md:flex-row md:items-center justify-between p-3.5 sm:p-4 rounded-xl bg-[#0b162c]/60 border border-slate-800 hover:border-slate-700 transition-all gap-3">
            <div className="flex flex-wrap items-baseline gap-2 sm:gap-4">
              <span className="text-sm font-semibold text-slate-300">
                Your IP Address (IPv6)
              </span>
              <div className="flex items-center gap-2">
                {data.ipv6 ? (
                  <span className="font-mono text-base sm:text-xl font-bold text-cyan-400 tracking-wide select-all">
                    {data.ipv6}
                  </span>
                ) : (
                  <span className="text-sm sm:text-base font-medium text-amber-400/90 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    IPv6: Not Detected
                  </span>
                )}
                <button
                  onClick={() => setShowIpv6Help(!showIpv6Help)}
                  className="text-slate-400 hover:text-slate-200 transition-colors"
                  title="Why is IPv6 not detected?"
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {data.ipv6 && (
              <button
                onClick={() => copyToClipboard(data.ipv6!, false)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center gap-1.5"
              >
                {copiedV6 ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                <span>{copiedV6 ? "Copied" : "Copy"}</span>
              </button>
            )}
          </div>

          {/* Help collapsible if user taps help icon */}
          {showIpv6Help && (
            <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-600/30 text-xs text-amber-200 space-y-1 animate-in fade-in">
              <p className="font-semibold">Why is IPv6 Not Detected?</p>
              <p className="text-amber-200/80">
                Your Internet Service Provider ({data.connection.isp || "ISP"}) or home router may currently only assign IPv4 addresses, or IPv6 is disabled in your network adapter settings. This is completely standard and safe for everyday web browsing.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import React, { useState } from "react";
import { X, ExternalLink, Sparkles, Database, Search } from "lucide-react";

export function LeftSkyscraper() {
  const [closed, setClosed] = useState(false);
  if (closed) return null;

  return (
    <aside className="hidden 2xl:block w-44 shrink-0 self-start sticky top-24">
      <div className="relative rounded-2xl bg-gradient-to-b from-[#0f2146] via-[#09152e] to-[#071024] border border-blue-500/25 p-4 shadow-xl text-center space-y-4">
        <button
          onClick={() => setClosed(true)}
          className="absolute top-2 right-2 p-1 text-slate-500 hover:text-slate-300"
          title="Close Ad"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        <span className="text-[10px] text-slate-400 uppercase tracking-widest block">
          Sponsored
        </span>

        <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg">
          <Sparkles className="w-6 h-6 text-white" />
        </div>

        <div className="space-y-2">
          <h4 className="text-base font-extrabold text-white leading-tight">
            Global High-Speed Proxy &amp; VPN
          </h4>
          <p className="text-[11px] text-slate-400 leading-snug">
            Secure your connection with 10Gbps servers in over 90+ countries.
          </p>
        </div>

        <div className="pt-2">
          <a
            href="#network-security"
            className="w-full py-2 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center justify-center gap-1 shadow-md transition-all"
          >
            <span>Learn More</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
    </aside>
  );
}

export function RightSkyscraper() {
  const [closed, setClosed] = useState(false);
  if (closed) return null;

  return (
    <aside className="hidden 2xl:block w-44 shrink-0 self-start sticky top-24">
      <div className="relative rounded-2xl bg-[#0b1426] border border-slate-800 p-4 shadow-xl text-center space-y-4">
        <button
          onClick={() => setClosed(true)}
          className="absolute top-2 right-2 p-1 text-slate-500 hover:text-slate-300"
          title="Close Ad"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        <span className="text-[10px] text-slate-400 uppercase tracking-widest block">
          Ad · Apify
        </span>

        <div className="w-12 h-12 mx-auto rounded-xl bg-[#1e293b] border border-slate-700 flex items-center justify-center shadow-lg">
          <Database className="w-6 h-6 text-emerald-400" />
        </div>

        <div className="space-y-2">
          <h4 className="text-sm font-bold text-slate-100 leading-tight">
            Search Instagram by Location
          </h4>
          <p className="text-[11px] text-slate-400 leading-snug">
            Scrape posts, reels, and profiles with web automation actors.
          </p>
        </div>

        <div className="pt-2">
          <a
            href="https://apify.com"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full py-2 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center justify-center gap-1 shadow-md transition-all"
          >
            <span>Try for free</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
    </aside>
  );
}

"use client";

import React, { useState } from "react";
import { X, ExternalLink, Sparkles } from "lucide-react";

export function TopAdBanner() {
  const [closed, setClosed] = useState(false);

  if (closed) return null;

  return (
    <div className="w-full max-w-4xl mx-auto my-4 px-4">
      <div className="relative group overflow-hidden rounded-xl bg-gradient-to-r from-[#0d1c3a] via-[#122b5c] to-[#0e2147] border border-blue-500/20 p-3 sm:p-4 shadow-lg flex items-center justify-between gap-4 transition-all hover:border-blue-400/40">
        {/* Subtle glow effect */}
        <div className="absolute -top-12 -left-12 w-32 h-32 bg-blue-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="flex items-center gap-3.5 sm:gap-5 z-10">
          {/* Sponsor stylized icon/badge */}
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-500 via-blue-500 to-cyan-400 p-0.5 shrink-0 shadow-md flex items-center justify-center">
            <div className="w-full h-full bg-[#0d1629] rounded-[10px] flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-cyan-400" />
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/20 text-cyan-300 border border-blue-500/30">
                Partner
              </span>
              <span className="text-xs font-semibold text-blue-200">
                Global Network Partner
              </span>
            </div>
            <h4 className="text-sm sm:text-base font-bold text-white tracking-tight mt-0.5">
              Protect Your Digital Identity &amp; Maximize Speed
            </h4>
            <p className="text-xs text-slate-300 hidden sm:block">
              Experience ultra-fast global endpoints with enterprise-grade encryption and 99.9% uptime.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 z-10">
          <a
            href="#partner"
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-medium text-xs sm:text-sm shadow-md shadow-blue-900/30 transition-all flex items-center gap-1.5 active:scale-95"
          >
            <span>Learn More</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
          <button
            onClick={() => setClosed(true)}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-white/5 transition-colors"
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

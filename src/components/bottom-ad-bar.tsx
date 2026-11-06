"use client";

import React, { useState } from "react";
import { X, ExternalLink, Sparkles } from "lucide-react";

export function BottomAdBar() {
  const [closed, setClosed] = useState(false);

  if (closed) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-30 flex justify-center p-2 sm:p-3 pointer-events-none">
      <div className="pointer-events-auto max-w-2xl w-full bg-[#0a162e]/95 border border-cyan-500/30 rounded-xl shadow-2xl backdrop-blur-md px-4 py-2.5 flex items-center justify-between gap-3 animate-in slide-in-from-bottom duration-300">
        <div className="flex items-center gap-3 truncate">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div className="truncate">
            <span className="text-[10px] text-cyan-400 font-semibold uppercase tracking-wider block">
              Sponsored
            </span>
            <p className="text-xs sm:text-sm font-bold text-white truncate">
              Protect Your Digital Identity with Encrypted VPN
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <a
            href="#vpn"
            className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs uppercase tracking-wider shadow-md flex items-center gap-1 transition-all active:scale-95"
          >
            <span>Open</span>
            <ExternalLink className="w-3 h-3" />
          </a>
          <button
            onClick={() => setClosed(true)}
            className="p-1 text-slate-400 hover:text-white rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

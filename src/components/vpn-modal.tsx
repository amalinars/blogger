"use client";

import React from "react";
import { X, ShieldCheck, Lock, CheckCircle, ExternalLink, Zap } from "lucide-react";
import { IpData } from "@/lib/types";

interface VpnModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: IpData;
}

export function VpnModal({ isOpen, onClose, data }: VpnModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-[#0b162c] border border-blue-500/30 rounded-2xl p-6 shadow-2xl text-slate-100">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-red-600 to-rose-500 flex items-center justify-center shadow-lg shadow-red-600/30">
            <Lock className="w-6 h-6 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Protect Your Online Privacy</h3>
            <p className="text-xs text-slate-400">
              Your real IP <span className="text-cyan-400 font-mono font-semibold">{data.ip}</span> is publicly visible
            </p>
          </div>
        </div>

        <div className="space-y-3 mb-6 text-xs text-slate-300">
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
            <div className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span>
                <strong>Mask your location:</strong> Websites and advertisers cannot see your true city ({data.city}) or ISP ({data.connection.isp}).
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span>
                <strong>Military-grade encryption:</strong> Protect passwords, banking details, and traffic on public Wi-Fi.
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span>
                <strong>Bypass geo-restrictions:</strong> Access global streaming, websites, and content from 100+ countries.
              </span>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <a
            href="https://nordvpn.com"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white font-bold text-sm shadow-lg shadow-red-900/30 flex items-center justify-center gap-2 transition-all active:scale-95"
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Get 70% Off Recommended VPN</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
          <button
            onClick={onClose}
            className="w-full py-2.5 text-xs text-slate-400 hover:text-white transition-colors text-center"
          >
            I understand the risks, continue browsing
          </button>
        </div>
      </div>
    </div>
  );
}

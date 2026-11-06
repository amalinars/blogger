"use client";

import React, { useState } from "react";
import { Bell, X, ShieldAlert, AlertTriangle, Eye } from "lucide-react";
import { IpData } from "@/lib/types";

interface NotificationBellProps {
  data: IpData;
}

export function NotificationBell({ data }: NotificationBellProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(3);

  const toggleOpen = () => {
    setIsOpen(!isOpen);
    if (!isOpen) {
      setUnreadCount(0);
    }
  };

  return (
    <div className="fixed bottom-5 left-5 z-40">
      {/* Popover */}
      {isOpen && (
        <div className="mb-3 w-80 bg-[#0c1833] border border-blue-500/40 rounded-2xl shadow-2xl p-4 text-slate-200 animate-in fade-in slide-in-from-bottom-2">
          <div className="flex items-center justify-between border-b border-slate-700/80 pb-2 mb-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-cyan-400" />
              Security Notifications
            </h4>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="p-2.5 rounded-xl bg-red-950/40 border border-red-500/30 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-200">Public IP Exposed</p>
                <p className="text-[11px] text-red-300/80">
                  Your address {data.ip} is unencrypted to visited servers.
                </p>
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 flex items-start gap-2">
              <Eye className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-slate-200">Geolocation Shared</p>
                <p className="text-[11px] text-slate-400">
                  Approximate location detected as {data.city}, {data.country}.
                </p>
              </div>
            </div>

            <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-slate-200">DNS Leak Advisory</p>
                <p className="text-[11px] text-slate-400">
                  DNS queries are processed by your ISP ({data.connection.isp}).
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Floating Bell Button (Matches screenshot) */}
      <button
        onClick={toggleOpen}
        className="relative w-12 h-12 rounded-full bg-gradient-to-tr from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white shadow-xl shadow-blue-900/40 flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        title="Privacy Notifications"
      >
        <Bell className="w-5 h-5 text-white" />

        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white font-bold text-[11px] flex items-center justify-center border-2 border-[#070c18] animate-pulse">
            {unreadCount}
          </span>
        )}
      </button>
    </div>
  );
}

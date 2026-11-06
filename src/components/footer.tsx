"use client";

import React from "react";
import { Shield, ExternalLink } from "lucide-react";
import { ActiveTab } from "./navbar";

interface FooterProps {
  onSelectTab?: (tab: ActiveTab) => void;
}

export function Footer({ onSelectTab }: FooterProps) {
  return (
    <footer className="w-full bg-[#050a14] border-t border-slate-800/80 text-slate-400 mt-16 pb-20 sm:pb-12 text-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
          <div>
            <h5 className="font-bold text-slate-200 uppercase tracking-wider mb-3 text-[11px]">
              IP Tools
            </h5>
            <ul className="space-y-2">
              <li>
                <button
                  onClick={() => onSelectTab?.("speedtest")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  Internet Speed Test
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("whois")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  IP Whois Lookup
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("lookup")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  IP Geolocation Lookup
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("dns")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  DNS &amp; MX Lookup
                </button>
              </li>
            </ul>
          </div>

          <div>
            <h5 className="font-bold text-slate-200 uppercase tracking-wider mb-3 text-[11px]">
              Privacy &amp; Security
            </h5>
            <ul className="space-y-2">
              <li>
                <button
                  onClick={() => onSelectTab?.("privacy")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  WebRTC Leak Test
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("privacy")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  DNS Leak Diagnostic
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("privacy")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  Proxy &amp; VPN Detection
                </button>
              </li>
              <li>
                <button
                  onClick={() => onSelectTab?.("my-ip")}
                  className="hover:text-cyan-400 transition-colors text-left"
                >
                  My IP Details
                </button>
              </li>
            </ul>
          </div>

          <div>
            <h5 className="font-bold text-slate-200 uppercase tracking-wider mb-3 text-[11px]">
              Developer API
            </h5>
            <ul className="space-y-2">
              <li>
                <a
                  href="/api/ip"
                  target="_blank"
                  className="hover:text-cyan-400 transition-colors flex items-center gap-1"
                >
                  IP Geolocation API (/api/ip) <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a
                  href="/api/whois?query=8.8.8.8"
                  target="_blank"
                  className="hover:text-cyan-400 transition-colors flex items-center gap-1"
                >
                  WHOIS RDAP API (/api/whois) <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <a
                  href="/api/dns?name=google.com&type=A"
                  target="_blank"
                  className="hover:text-cyan-400 transition-colors flex items-center gap-1"
                >
                  DNS DoH API (/api/dns) <ExternalLink className="w-3 h-3" />
                </a>
              </li>
              <li>
                <span className="text-emerald-400 flex items-center gap-1">
                  ● API Status: Operational
                </span>
              </li>
            </ul>
          </div>

          <div>
            <h5 className="font-bold text-slate-200 uppercase tracking-wider mb-3 text-[11px]">
              About IPRadar
            </h5>
            <p className="text-slate-400 leading-relaxed mb-3">
              Global platform for public IP address detection, geographic telemetry, network diagnostic tools, and cybersecurity privacy auditing.
            </p>
            <div className="flex items-center gap-2 text-slate-300">
              <Shield className="w-4 h-4 text-cyan-400" />
              <span>TLS 1.3 256-bit Encrypted</span>
            </div>
          </div>
        </div>

        <div className="border-t border-slate-800/80 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px]">
          <p>© {new Date().getFullYear()} IPRadar.io. All rights reserved. Global Network Intelligence.</p>
          <div className="flex items-center space-x-4">
            <a href="#privacy" className="hover:text-slate-200 transition-colors">Privacy Policy</a>
            <span>•</span>
            <a href="#terms" className="hover:text-slate-200 transition-colors">Terms of Service</a>
            <span>•</span>
            <a href="#contact" className="hover:text-slate-200 transition-colors">Network Status</a>
          </div>
        </div>
      </div>
    </footer>
  );
}

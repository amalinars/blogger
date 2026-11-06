"use client";

import React, { useState } from "react";
import {
  Globe,
  Search,
  ChevronDown,
  Menu,
  X,
  ShieldCheck,
  Zap,
} from "lucide-react";

export type ActiveTab = "my-ip" | "lookup" | "whois" | "speedtest" | "dns" | "privacy";

interface NavbarProps {
  onSearch: (query: string) => void;
  isLoading?: boolean;
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
}

export function Navbar({ onSearch, isLoading = false, activeTab, onSelectTab }: NavbarProps) {
  const [searchVal, setSearchVal] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchVal.trim()) {
      onSearch(searchVal.trim());
      onSelectTab("lookup");
    }
  };

  const toggleDropdown = (name: string) => {
    setOpenDropdown(openDropdown === name ? null : name);
  };

  return (
    <header className="w-full bg-[#091122] border-b border-slate-800/80 sticky top-0 z-50 shadow-xl">
      {/* Top Navbar */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          {/* Logo */}
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => {
                onSearch("");
                onSelectTab("my-ip");
              }}
              className="flex items-center gap-2 group text-left"
            >
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform">
                <Globe className="w-5 h-5 text-white animate-spin-slow" />
              </div>
              <div className="flex items-baseline">
                <span className="text-xl font-bold tracking-tight text-white group-hover:text-cyan-400 transition-colors">
                  IPRadar
                </span>
                <span className="text-cyan-400 font-semibold text-sm">.io</span>
                <span className="text-[10px] text-slate-400 font-medium ml-1.5 hidden sm:inline px-1.5 py-0.2 rounded bg-slate-800 border border-slate-700/60">
                  NETWORK SUITE
                </span>
              </div>
            </button>
          </div>

          {/* Search Bar */}
          <div className="hidden md:flex flex-1 max-w-md mx-4">
            <form onSubmit={handleSubmit} className="relative w-full">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Lookup any IP or domain (e.g. 8.8.8.8)..."
                value={searchVal}
                onChange={(e) => setSearchVal(e.target.value)}
                className="w-full bg-[#0f1b33] border border-slate-700/80 rounded-lg pl-10 pr-24 py-1.5 text-sm text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all"
              />
              <button
                type="submit"
                disabled={isLoading}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium rounded-md transition-all flex items-center gap-1 shadow-sm disabled:opacity-60"
              >
                {isLoading ? (
                  <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  "Lookup"
                )}
              </button>
            </form>
          </div>

          {/* Right Links */}
          <div className="hidden lg:flex items-center gap-4 text-xs font-semibold text-slate-300">
            <button
              onClick={() => onSelectTab("speedtest")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-cyan-300 border border-slate-700 transition-colors"
            >
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
              <span>Speed Test</span>
            </button>

            <button
              onClick={() => onSelectTab("privacy")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-emerald-300 border border-slate-700 transition-colors"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Leak Test</span>
            </button>
          </div>

          {/* Mobile menu button */}
          <div className="flex md:hidden items-center gap-2">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>

        {/* Mobile Search Input */}
        <div className="md:hidden pb-3">
          <form onSubmit={handleSubmit} className="relative w-full">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search IP or domain..."
              value={searchVal}
              onChange={(e) => setSearchVal(e.target.value)}
              className="w-full bg-[#0f1b33] border border-slate-700/80 rounded-lg pl-10 pr-20 py-2 text-sm text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            />
            <button
              type="submit"
              disabled={isLoading}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 px-3 py-1 bg-cyan-600 text-white text-xs font-medium rounded-md"
            >
              {isLoading ? "..." : "Lookup"}
            </button>
          </form>
        </div>
      </div>

      {/* Secondary Ribbon Navigation (Blue Bar) */}
      <div className="w-full bg-gradient-to-r from-blue-700 via-blue-600 to-indigo-700 text-white shadow-inner">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex items-center space-x-1 sm:space-x-2 py-1.5 overflow-x-auto no-scrollbar text-xs sm:text-sm font-medium">
            <button
              onClick={() => onSelectTab("my-ip")}
              className={`px-3 py-1.5 rounded-md text-white font-semibold shrink-0 transition-all ${
                activeTab === "my-ip" ? "bg-white/25 shadow-sm" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              My IP Address
            </button>

            <button
              onClick={() => onSelectTab("lookup")}
              className={`px-3 py-1.5 rounded-md font-semibold shrink-0 transition-all ${
                activeTab === "lookup" ? "bg-white/25 shadow-sm text-white" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              IP Address Lookup
            </button>

            <button
              onClick={() => onSelectTab("whois")}
              className={`px-3 py-1.5 rounded-md font-semibold shrink-0 transition-all ${
                activeTab === "whois" ? "bg-white/25 shadow-sm text-white" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              IP Whois Lookup
            </button>

            <button
              onClick={() => onSelectTab("speedtest")}
              className={`px-3 py-1.5 rounded-md font-semibold shrink-0 transition-all ${
                activeTab === "speedtest" ? "bg-white/25 shadow-sm text-white" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              Speed Test
            </button>

            <button
              onClick={() => onSelectTab("dns")}
              className={`px-3 py-1.5 rounded-md font-semibold shrink-0 transition-all ${
                activeTab === "dns" ? "bg-white/25 shadow-sm text-white" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              DNS Records
            </button>

            <button
              onClick={() => onSelectTab("privacy")}
              className={`px-3 py-1.5 rounded-md font-semibold shrink-0 transition-all ${
                activeTab === "privacy" ? "bg-white/25 shadow-sm text-white" : "hover:bg-white/10 text-blue-100"
              }`}
            >
              Privacy &amp; Leak Test
            </button>

            {/* Quick Tools Dropdown */}
            <div className="relative shrink-0">
              <button
                onClick={() => toggleDropdown("tools")}
                className="flex items-center gap-1 px-3 py-1.5 rounded-md text-blue-100 hover:text-white hover:bg-white/10 transition-all"
              >
                <span>More Tools</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
              {openDropdown === "tools" && (
                <div className="absolute left-0 mt-2 w-52 bg-[#0c1830] border border-blue-500/30 rounded-xl shadow-2xl py-2 z-50 animate-in fade-in slide-in-from-top-1 text-slate-200">
                  <button
                    onClick={() => {
                      onSelectTab("dns");
                      setOpenDropdown(null);
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-blue-600/30 hover:text-cyan-300"
                  >
                    DNS &amp; MX Lookup
                  </button>
                  <button
                    onClick={() => {
                      onSelectTab("whois");
                      setOpenDropdown(null);
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-blue-600/30 hover:text-cyan-300"
                  >
                    ASN &amp; RDAP Check
                  </button>
                  <button
                    onClick={() => {
                      onSelectTab("speedtest");
                      setOpenDropdown(null);
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-blue-600/30 hover:text-cyan-300"
                  >
                    Latency &amp; Jitter Ping
                  </button>
                  <button
                    onClick={() => {
                      onSelectTab("privacy");
                      setOpenDropdown(null);
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-blue-600/30 hover:text-cyan-300"
                  >
                    WebRTC Leak Diagnostic
                  </button>
                </div>
              )}
            </div>
          </nav>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#0a1329] border-b border-slate-800 p-4 space-y-2 text-sm text-slate-200">
          <button
            onClick={() => {
              onSelectTab("my-ip");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            My IP Address
          </button>
          <button
            onClick={() => {
              onSelectTab("lookup");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            IP Address Lookup
          </button>
          <button
            onClick={() => {
              onSelectTab("whois");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            IP Whois Lookup
          </button>
          <button
            onClick={() => {
              onSelectTab("speedtest");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            Internet Speed Test
          </button>
          <button
            onClick={() => {
              onSelectTab("dns");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            DNS Records
          </button>
          <button
            onClick={() => {
              onSelectTab("privacy");
              setMobileMenuOpen(false);
            }}
            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800"
          >
            Privacy &amp; Leak Test
          </button>
        </div>
      )}
    </header>
  );
}

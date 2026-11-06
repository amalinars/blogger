"use client";

import React, { useState } from "react";
import { Search, FileText, Check, Copy, RefreshCw, AlertCircle } from "lucide-react";

interface WhoisToolProps {
  initialIp: string;
}

interface WhoisResult {
  success: boolean;
  ip: string;
  domain?: string;
  hostname?: string;
  netName?: string;
  handle?: string;
  startAddress?: string;
  endAddress?: string;
  cidr?: string;
  status?: string;
  asn?: number;
  org?: string;
  isp?: string;
  country?: string;
  countryCode?: string;
  city?: string;
  rawWhois?: string;
  error?: string;
}

export function WhoisTool({ initialIp }: WhoisToolProps) {
  const [query, setQuery] = useState(initialIp || "8.8.8.8");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [result, setResult] = useState<WhoisResult | null>(null);

  const fetchWhois = async (targetQuery?: string) => {
    const q = (targetQuery || query).trim();
    if (!q) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/whois?query=${encodeURIComponent(q)}`);
      const data: WhoisResult = await res.json();
      setResult(data);
    } catch {
      setResult({
        success: false,
        ip: q,
        error: "Failed to fetch WHOIS/RDAP records. Please verify the host.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result?.rawWhois) return;
    navigator.clipboard.writeText(result.rawWhois);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const presets = [
    { label: "My IP", val: initialIp },
    { label: "Google (8.8.8.8)", val: "8.8.8.8" },
    { label: "Cloudflare (1.1.1.1)", val: "1.1.1.1" },
    { label: "OpenDNS (208.67.222.222)", val: "208.67.222.222" },
    { label: "Quad9 (9.9.9.9)", val: "9.9.9.9" },
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Search Header Banner */}
      <div className="rounded-2xl bg-gradient-to-r from-[#0d1c3a] via-[#102347] to-[#09152e] border border-blue-500/30 p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-1">
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-500/20 text-cyan-300 border border-blue-500/30">
            Official RIR &amp; RDAP Database
          </span>
          <span className="text-xs text-slate-400">ARIN · RIPE · APNIC · LACNIC · AFRINIC</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
          IP Whois &amp; Network Ownership Lookup
        </h2>
        <p className="text-xs text-slate-300 mt-1 max-w-2xl">
          Retrieve registered network allocation, ASN origin, IP CIDR range, netname, organization, and abuse contact information.
        </p>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            fetchWhois();
          }}
          className="mt-5 flex flex-col sm:flex-row gap-2"
        >
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Enter IP address (e.g. 1.1.1.1) or domain (e.g. cloudflare.com)..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-[#0a1529] border border-slate-700/80 rounded-xl pl-10 pr-4 py-3 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-60"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
            <span>Lookup Whois</span>
          </button>
        </form>

        {/* Quick Presets */}
        <div className="flex items-center gap-2 mt-4 flex-wrap text-xs">
          <span className="text-slate-400 text-[11px] font-semibold">Presets:</span>
          {presets.map((p) => (
            <button
              key={p.val}
              onClick={() => {
                setQuery(p.val);
                fetchWhois(p.val);
              }}
              className="px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors border border-slate-700/60"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results View */}
      {result && (
        <div className="space-y-6 animate-in slide-in-from-bottom-2 duration-300">
          {result.error ? (
            <div className="rounded-2xl bg-red-950/40 border border-red-500/30 p-5 flex items-center gap-3 text-red-200 text-sm">
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
              <span>{result.error}</span>
            </div>
          ) : (
            <>
              {/* Summary 4-Card Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-4 shadow-xl">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
                    NetName &amp; Range
                  </span>
                  <p className="text-base font-bold text-white truncate">{result.netName || "--"}</p>
                  <p className="text-xs text-cyan-400 font-mono mt-1 truncate">{result.cidr || "--"}</p>
                </div>

                <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-4 shadow-xl">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
                    Autonomous System
                  </span>
                  <p className="text-base font-bold text-white">AS{result.asn || "--"}</p>
                  <p className="text-xs text-slate-400 truncate mt-1">{result.org || "--"}</p>
                </div>

                <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-4 shadow-xl">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
                    Organization / ISP
                  </span>
                  <p className="text-base font-bold text-white truncate">{result.isp || "--"}</p>
                  <p className="text-xs text-slate-400 mt-1 truncate">{result.handle || "--"}</p>
                </div>

                <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-4 shadow-xl">
                  <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
                    Country &amp; Geolocation
                  </span>
                  <p className="text-base font-bold text-white truncate">
                    {result.city}, {result.country}
                  </p>
                  <p className="text-xs text-emerald-400 mt-1">Status: {result.status || "Active"}</p>
                </div>
              </div>

              {/* Raw WHOIS Text Output Block */}
              <div className="rounded-2xl bg-[#081020] border border-slate-800 p-5 shadow-2xl relative overflow-hidden">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
                    <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
                      RDAP / WHOIS Records Output
                    </span>
                  </div>
                  <button
                    onClick={handleCopy}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center gap-1.5 transition-colors"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? "Copied" : "Copy Raw"}</span>
                  </button>
                </div>

                <pre className="font-mono text-xs sm:text-sm text-cyan-300/90 whitespace-pre-wrap leading-relaxed overflow-x-auto max-h-96 p-2 rounded bg-black/40 border border-slate-900 selection:bg-cyan-500 selection:text-black">
                  {result.rawWhois}
                </pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

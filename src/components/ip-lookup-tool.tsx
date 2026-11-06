"use client";

import React, { useState } from "react";
import { Search, MapPin, Server, Clock, RefreshCw, AlertCircle, ExternalLink } from "lucide-react";
import { IpData } from "@/lib/types";

interface IpLookupToolProps {
  initialIp: string;
}

export function IpLookupTool({ initialIp }: IpLookupToolProps) {
  const [query, setQuery] = useState(initialIp || "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IpData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const performLookup = async (targetIp?: string) => {
    const q = (targetIp !== undefined ? targetIp : query).trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/ip?query=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.error || "Could not resolve IP address.");
      }
      setResult(data);
    } catch (err: unknown) {
      setError((err as Error)?.message || "IP lookup failed. Please check the address.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const presets = [
    { label: "My Current IP", val: initialIp },
    { label: "Cloudflare (1.1.1.1)", val: "1.1.1.1" },
    { label: "Google DNS (8.8.8.8)", val: "8.8.8.8" },
    { label: "OpenDNS (208.67.222.222)", val: "208.67.222.222" },
    { label: "Quad9 (9.9.9.9)", val: "9.9.9.9" },
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Banner & Search Bar */}
      <div className="rounded-2xl bg-gradient-to-r from-[#0d1c3a] via-[#102347] to-[#09152e] border border-blue-500/30 p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-1">
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Global Geolocation Engine
          </span>
          <span className="text-xs text-slate-400">High-Precision IP Mapping &amp; Carrier Telemetry</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
          IP Address Lookup &amp; Geolocation
        </h2>
        <p className="text-xs text-slate-300 mt-1 max-w-2xl">
          Enter any IPv4, IPv6, or domain name to discover its geographic location, internet service provider, autonomous system, and timezone.
        </p>

        {/* Input Form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            performLookup();
          }}
          className="mt-5 flex flex-col sm:flex-row gap-2"
        >
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search any IP (e.g. 8.8.8.8) or domain (e.g. google.com)..."
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
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <MapPin className="w-4 h-4" />}
            <span>Lookup IP</span>
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
                performLookup(p.val);
              }}
              className="px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors border border-slate-700/60"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-2xl bg-red-950/40 border border-red-500/30 p-5 flex items-center gap-3 text-red-200 text-sm animate-in fade-in">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Results View */}
      {result && (
        <div className="space-y-6 animate-in slide-in-from-bottom-2 duration-300">
          {/* Top Primary Card */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-6 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="text-4xl p-2 rounded-xl bg-slate-800/80 border border-slate-700/60">
                {result.flag?.emoji || "🌐"}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-2xl sm:text-3xl font-black text-white font-mono tracking-tight">
                    {result.ip}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-500/20 text-cyan-300 border border-blue-500/30">
                    {result.type}
                  </span>
                </div>
                <p className="text-sm text-slate-300">
                  {result.city}, {result.region}, {result.country} ({result.country_code})
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={`https://maps.google.com/?q=${result.latitude},${result.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-colors border border-slate-700/60"
              >
                <span>View Google Maps</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>

          {/* 3-Column Detailed Attributes */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Column 1: Geolocation */}
            <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl space-y-3">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
                <MapPin className="w-4 h-4 text-cyan-400" />
                <h4 className="text-sm font-bold text-white">Geographic Location</h4>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Continent</span>
                  <span className="text-white font-medium">{result.continent} ({result.continent_code})</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Country</span>
                  <span className="text-white font-medium">{result.country} ({result.country_code})</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">State / Region</span>
                  <span className="text-white font-medium">{result.region}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">City / Postal</span>
                  <span className="text-white font-medium">{result.city} · {result.postal || "N/A"}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Coordinates</span>
                  <span className="text-cyan-400 font-mono font-medium">{result.latitude}, {result.longitude}</span>
                </div>
              </div>
            </div>

            {/* Column 2: Network & ISP */}
            <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl space-y-3">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
                <Server className="w-4 h-4 text-blue-400" />
                <h4 className="text-sm font-bold text-white">Network &amp; Carrier</h4>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">ASN</span>
                  <span className="text-cyan-400 font-mono font-bold">AS{result.connection.asn}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">ISP Provider</span>
                  <span className="text-white font-medium truncate max-w-[150px]">{result.connection.isp}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Organization</span>
                  <span className="text-white font-medium truncate max-w-[150px]">{result.connection.org}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Carrier Domain</span>
                  <span className="text-white font-mono">{result.connection.domain || "N/A"}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Calling Code</span>
                  <span className="text-white font-medium">+{result.calling_code || "N/A"}</span>
                </div>
              </div>
            </div>

            {/* Column 3: Timezone & Coordinates */}
            <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl space-y-3">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
                <Clock className="w-4 h-4 text-emerald-400" />
                <h4 className="text-sm font-bold text-white">Timezone &amp; Local Time</h4>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Timezone ID</span>
                  <span className="text-white font-medium">{result.timezone.id}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">UTC Offset</span>
                  <span className="text-cyan-400 font-mono font-bold">UTC {result.timezone.utc}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800/40">
                  <span className="text-slate-400">Abbreviation</span>
                  <span className="text-white font-medium">{result.timezone.abbr || "N/A"}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Capital City</span>
                  <span className="text-white font-medium">{result.capital || "N/A"}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Interactive Map Frame */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-4 shadow-xl overflow-hidden">
            <div className="flex items-center justify-between mb-3 px-1">
              <span className="text-xs font-bold text-slate-300">Target Geolocation Satellite Preview</span>
              <span className="text-[11px] text-slate-400 font-mono">
                Lat: {result.latitude.toFixed(4)}, Lon: {result.longitude.toFixed(4)}
              </span>
            </div>
            <div className="w-full h-72 rounded-xl overflow-hidden border border-slate-800 relative bg-[#070c18]">
              <iframe
                title="Location Map"
                className="w-full h-full border-0 filter brightness-90 contrast-125"
                src={`https://www.openstreetmap.org/export/embed.html?bbox=${result.longitude - 0.08}%2C${result.latitude - 0.05}%2C${result.longitude + 0.08}%2C${result.latitude + 0.05}&layer=mapnik&marker=${result.latitude}%2C${result.longitude}`}
                loading="lazy"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

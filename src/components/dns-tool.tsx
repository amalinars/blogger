"use client";

import React, { useState } from "react";
import { Search, Globe, Network, RefreshCw, AlertCircle, Copy, Check } from "lucide-react";

interface DnsAnswer {
  name: string;
  type: number;
  ttl: number;
  data: string;
}

const RECORD_TYPES = ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"];

export function DnsTool() {
  const [domain, setDomain] = useState("cloudflare.com");
  const [recordType, setRecordType] = useState("A");
  const [loading, setLoading] = useState(false);
  const [answers, setAnswers] = useState<DnsAnswer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const fetchDns = async (targetDomain?: string, targetType?: string) => {
    const d = (targetDomain || domain).trim();
    const t = (targetType || recordType).toUpperCase();
    if (!d) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/dns?name=${encodeURIComponent(d)}&type=${encodeURIComponent(t)}`);
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "DNS resolution failed");
      }
      setAnswers(data.answers || []);
    } catch (err: unknown) {
      setError((err as Error)?.message || "Failed to query DNS records.");
      setAnswers(null);
    } finally {
      setLoading(false);
    }
  };

  const copyRow = (val: string, idx: number) => {
    navigator.clipboard.writeText(val);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const presets = ["cloudflare.com", "google.com", "github.com", "wikipedia.org", "microsoft.com"];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Banner & Control Card */}
      <div className="rounded-2xl bg-gradient-to-r from-[#0d1c3a] via-[#102347] to-[#09152e] border border-blue-500/30 p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-1">
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Authoritative DNS-over-HTTPS (DoH)
          </span>
          <span className="text-xs text-slate-400">RFC 8484 Global Root Resolvers</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
          DNS &amp; Reverse DNS Record Lookup
        </h2>
        <p className="text-xs text-slate-300 mt-1 max-w-2xl">
          Inspect live authoritative DNS resource records including A, AAAA, MX mail servers, TXT verification keys, and NS nameservers.
        </p>

        {/* Input Form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            fetchDns();
          }}
          className="mt-5 flex flex-col sm:flex-row gap-2"
        >
          <div className="relative flex-1">
            <Globe className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Enter domain name (e.g. google.com)..."
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full bg-[#0a1529] border border-slate-700/80 rounded-xl pl-10 pr-4 py-3 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-60"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            <span>Query DNS</span>
          </button>
        </form>

        {/* Record Type Selector */}
        <div className="flex items-center gap-2 mt-4 flex-wrap">
          <span className="text-slate-400 text-xs font-semibold">Record Type:</span>
          {RECORD_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => {
                setRecordType(type);
                fetchDns(domain, type);
              }}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                recordType === type
                  ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                  : "bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        {/* Quick Presets */}
        <div className="flex items-center gap-2 mt-3 flex-wrap text-xs text-slate-400">
          <span className="text-[11px] font-semibold">Examples:</span>
          {presets.map((p) => (
            <button
              key={p}
              onClick={() => {
                setDomain(p);
                fetchDns(p, recordType);
              }}
              className="hover:text-cyan-300 transition-colors underline underline-offset-2"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Results View */}
      {error && (
        <div className="rounded-2xl bg-red-950/40 border border-red-500/30 p-5 flex items-center gap-3 text-red-200 text-sm animate-in fade-in">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {answers && (
        <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-6 shadow-xl animate-in slide-in-from-bottom-2 duration-300 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">
                Resolved Records for <span className="text-cyan-400 font-mono">{domain}</span> ({recordType})
              </h3>
            </div>
            <span className="text-xs text-slate-400">{answers.length} record(s) found</span>
          </div>

          {answers.length === 0 ? (
            <div className="text-center py-8 text-slate-400 text-sm">
              No <span className="font-mono text-cyan-400">{recordType}</span> records found for {domain}.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-[#0e1c38] text-slate-400 uppercase text-[10px] tracking-wider font-bold">
                  <tr>
                    <th className="py-2.5 px-3 rounded-l-lg">Host / Name</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3">TTL</th>
                    <th className="py-2.5 px-3">Target / Record Value</th>
                    <th className="py-2.5 px-3 rounded-r-lg text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {answers.map((ans, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3 text-slate-200 truncate max-w-xs">{ans.name}</td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded bg-blue-500/20 text-cyan-300 border border-blue-500/30 font-bold">
                          {recordType}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-400">{ans.ttl}s</td>
                      <td className="py-3 px-3 text-cyan-300 break-all">{ans.data}</td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={() => copyRow(ans.data, idx)}
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                          title="Copy value"
                        >
                          {copiedIdx === idx ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

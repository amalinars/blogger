"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  Copy,
  Check,
  Shield,
  Lock,
  MapPin,
  Clock,
  Radio,
  Server,
  Building,
} from "lucide-react";
import { IpData } from "@/lib/types";

interface IpDetailsProps {
  data: IpData;
  onOpenVpnModal: () => void;
}

export function IpDetails({ data, onOpenVpnModal }: IpDetailsProps) {
  const [activeTab, setActiveTab] = useState<"ipv4" | "ipv6">("ipv4");
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const handleCopy = (field: string, value: string) => {
    navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1800);
  };

  const fields = [
    {
      key: "city",
      label: "City",
      value: data.city || "Jakarta",
      icon: MapPin,
    },
    {
      key: "region",
      label: "State/Region",
      value: data.region || "Jakarta Raya",
      icon: MapPin,
    },
    {
      key: "country",
      label: "Country",
      value: data.country || "Indonesia",
      flag: data.flag?.emoji || "🇮🇩",
      icon: MapPin,
    },
    {
      key: "postal",
      label: "Postal Code",
      value: data.postal || "12850",
      icon: MapPin,
    },
    {
      key: "timezone",
      label: "Time Zone",
      value: `UTC ${data.timezone.utc || "+07:00"}${data.timezone.abbr ? ` (${data.timezone.abbr})` : ""}`,
      icon: Clock,
    },
    {
      key: "isp",
      label: "ISP",
      value: data.connection.isp || "IOH B2B",
      icon: Radio,
    },
    {
      key: "asn",
      label: "ASN",
      value: String(data.connection.asn || "4761"),
      link: `https://bgp.he.net/AS${data.connection.asn || "4761"}`,
      icon: Server,
    },
  ];

  return (
    <div className="rounded-2xl bg-[#091326]/90 border border-slate-700/60 overflow-hidden shadow-2xl flex flex-col justify-between">
      <div>
        {/* Tab Headers (IPv4 Details / IPv6 Details) */}
        <div className="flex border-b border-slate-800 bg-[#070e1c]">
          <button
            onClick={() => setActiveTab("ipv4")}
            className={`flex-1 py-3 px-4 text-xs sm:text-sm font-semibold transition-all border-b-2 flex items-center justify-center gap-2 ${
              activeTab === "ipv4"
                ? "border-cyan-500 text-cyan-400 bg-[#0f1d38]/60 shadow-sm"
                : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <span>IPv4 Details</span>
            <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#22d3ee]" />
          </button>
          <button
            onClick={() => setActiveTab("ipv6")}
            className={`flex-1 py-3 px-4 text-xs sm:text-sm font-semibold transition-all border-b-2 flex items-center justify-center gap-2 ${
              activeTab === "ipv6"
                ? "border-cyan-500 text-cyan-400 bg-[#0f1d38]/60 shadow-sm"
                : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <span>IPv6 Details</span>
            <span className="w-2 h-2 rounded-full bg-slate-500" />
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-4 sm:p-5">
          {activeTab === "ipv4" ? (
            <div>
              {/* Red Alert Pill (VISIBLE FROM YOUR IP ADDRESS) */}
              <div className="mb-4 p-2.5 rounded-xl bg-red-950/40 border border-red-500/30 flex items-center gap-2.5 text-red-400">
                <div className="p-1 rounded-md bg-red-500/20 text-red-400 shrink-0">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] sm:text-xs font-bold tracking-wider uppercase">
                    Visible from your IP address
                  </span>
                  <span className="inline-block w-2 h-2 rounded-full bg-red-500 radar-dot" />
                </div>
              </div>

              {/* Data rows with copy icons */}
              <div className="divide-y divide-slate-800/80 text-xs sm:text-sm">
                {fields.map((f) => {
                  const isCopied = copiedField === f.key;
                  return (
                    <div
                      key={f.key}
                      className="py-2.5 flex items-center justify-between gap-3 group hover:bg-slate-800/30 px-2 rounded-lg transition-colors"
                    >
                      <span className="text-slate-400 font-medium">{f.label}:</span>
                      <div className="flex items-center gap-2 font-semibold text-slate-100 text-right">
                        {f.flag && <span className="text-base">{f.flag}</span>}
                        {f.link ? (
                          <a
                            href={f.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-cyan-400 hover:underline"
                          >
                            {f.value}
                          </a>
                        ) : (
                          <span>{f.value}</span>
                        )}
                        <button
                          onClick={() => handleCopy(f.key, f.value)}
                          className={`p-1 rounded transition-colors ${
                            isCopied
                              ? "text-emerald-400 bg-emerald-500/10"
                              : "text-slate-500 hover:text-slate-200 group-hover:text-slate-400"
                          }`}
                          title={`Copy ${f.label}`}
                        >
                          {isCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-slate-400 space-y-3">
              <div className="w-12 h-12 mx-auto rounded-full bg-slate-800/60 border border-slate-700 flex items-center justify-center text-slate-400">
                <Server className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-semibold text-slate-300">IPv6 Not Available</h4>
              <p className="text-xs text-slate-400 max-w-xs mx-auto">
                No public IPv6 address was routed for this request. Your network is communicating via standard IPv4.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* VPN CTA Button Box (Exact match from screenshot) */}
      <div className="p-4 sm:p-5 pt-0">
        <button
          onClick={onOpenVpnModal}
          className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-red-600 via-rose-600 to-red-700 hover:from-red-500 hover:to-rose-500 text-white font-bold text-xs sm:text-sm shadow-lg shadow-red-900/30 flex items-center justify-center gap-2 transition-all active:scale-[0.99] group"
        >
          <Lock className="w-4 h-4 group-hover:scale-110 transition-transform" />
          <span>Hide My IP Address with a VPN</span>
        </button>
        <p className="text-[11px] text-slate-400 text-center mt-2">
          A VPN helps hide your IP address and encrypt your Internet connection.
        </p>
      </div>
    </div>
  );
}

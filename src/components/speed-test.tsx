"use client";

import React, { useState, useRef, useEffect } from "react";
import { ArrowDown, ArrowUp, Zap, Activity, RefreshCw, Server, Wifi } from "lucide-react";
import { IpData } from "@/lib/types";

interface SpeedTestProps {
  data: IpData;
}

type TestPhase = "idle" | "ping" | "download" | "upload" | "finished";

export function SpeedTest({ data }: SpeedTestProps) {
  const [phase, setPhase] = useState<TestPhase>("idle");
  const [ping, setPing] = useState<number | null>(null);
  const [jitter, setJitter] = useState<number | null>(null);
  const [downloadSpeed, setDownloadSpeed] = useState<number | null>(null);
  const [uploadSpeed, setUploadSpeed] = useState<number | null>(null);
  const [currentSpeed, setCurrentSpeed] = useState<number>(0);
  const [progress, setProgress] = useState<number>(0);
  const [statusMsg, setStatusMsg] = useState<string>("Ready to test your connection speed");

  const abortControllerRef = useRef<AbortController | null>(null);

  const runTest = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setPhase("ping");
    setProgress(5);
    setStatusMsg("Measuring latency and jitter (5 pings)...");
    setPing(null);
    setJitter(null);
    setDownloadSpeed(null);
    setUploadSpeed(null);
    setCurrentSpeed(0);

    try {
      // 1. Measure Ping & Jitter (5 samples)
      const pings: number[] = [];
      for (let i = 0; i < 5; i++) {
        if (ac.signal.aborted) return;
        const start = performance.now();
        await fetch("/api/speedtest?ping=1&t=" + Date.now(), {
          cache: "no-store",
          signal: ac.signal,
        });
        const duration = performance.now() - start;
        pings.push(duration);
        setProgress(5 + (i + 1) * 3);
        const { promise: delayPromise, resolve: delayResolve } = Promise.withResolvers<void>();
        setTimeout(delayResolve, 60);
        await delayPromise;
      }

      const avgPing = Math.round(pings.reduce((a, b) => a + b, 0) / pings.length);
      let jitterSum = 0;
      for (let i = 1; i < pings.length; i++) {
        jitterSum += Math.abs(pings[i] - pings[i - 1]);
      }
      const avgJitter = Math.round(jitterSum / (pings.length - 1)) || 2;

      setPing(avgPing);
      setJitter(avgJitter);
      setProgress(25);

      // 2. Measure Download Speed
      setPhase("download");
      setStatusMsg("Testing download bandwidth...");

      let totalDownloadBytes = 0;
      const downloadStart = performance.now();
      const chunks = 3;

      for (let i = 0; i < chunks; i++) {
        if (ac.signal.aborted) return;
        const chunkStart = performance.now();
        const res = await fetch("/api/speedtest?download=1&size=3000000&c=" + i, {
          cache: "no-store",
          signal: ac.signal,
        });
        const blob = await res.blob();
        totalDownloadBytes += blob.size;

        const elapsed = (performance.now() - chunkStart) / 1000;
        const instantMbps = (blob.size * 8) / (elapsed * 1000000);
        setCurrentSpeed(Math.round(instantMbps * 10) / 10);
        setProgress(25 + ((i + 1) / chunks) * 35);
      }

      const totalDownloadTime = (performance.now() - downloadStart) / 1000;
      const finalDownloadMbps =
        Math.round(((totalDownloadBytes * 8) / (totalDownloadTime * 1000000)) * 10) / 10;
      setDownloadSpeed(finalDownloadMbps);
      setCurrentSpeed(finalDownloadMbps);
      setProgress(65);

      // 3. Measure Upload Speed
      setPhase("upload");
      setStatusMsg("Testing upload bandwidth...");

      const uploadPayload = new Uint8Array(1000000); // 1MB payload
      let totalUploadBytes = 0;
      const uploadStart = performance.now();
      const uploadChunks = 2;

      for (let i = 0; i < uploadChunks; i++) {
        if (ac.signal.aborted) return;
        const chunkStart = performance.now();
        await fetch("/api/speedtest", {
          method: "POST",
          body: uploadPayload,
          cache: "no-store",
          signal: ac.signal,
        });
        totalUploadBytes += uploadPayload.byteLength;

        const elapsed = (performance.now() - chunkStart) / 1000;
        const instantMbps = (uploadPayload.byteLength * 8) / (elapsed * 1000000);
        setCurrentSpeed(Math.round(instantMbps * 10) / 10);
        setProgress(65 + ((i + 1) / uploadChunks) * 35);
      }

      const totalUploadTime = (performance.now() - uploadStart) / 1000;
      const finalUploadMbps =
        Math.round(((totalUploadBytes * 8) / (totalUploadTime * 1000000)) * 10) / 10;
      setUploadSpeed(finalUploadMbps);
      setCurrentSpeed(finalUploadMbps);
      setProgress(100);

      setPhase("finished");
      setStatusMsg("Test completed successfully!");
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        console.error("Speedtest error:", err);
        setStatusMsg("Test interrupted or network error occurred.");
      }
      setPhase("idle");
    }
  };

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header Banner */}
      <div className="rounded-2xl bg-gradient-to-r from-[#0c1a36] via-[#10244d] to-[#0a162e] border border-blue-500/30 p-6 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              Live Network Benchmark
            </span>
            <span className="text-xs text-slate-400">Direct Socket Latency & Throughput</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Internet Speed Test &amp; Latency Benchmark
          </h2>
          <p className="text-xs text-slate-300 mt-1">
            Measure your accurate real-world download speed, upload bandwidth, ping latency, and jitter.
          </p>
        </div>

        <button
          onClick={runTest}
          disabled={phase !== "idle" && phase !== "finished"}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-600 via-blue-600 to-indigo-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-sm shadow-xl shadow-cyan-600/20 flex items-center gap-2 transition-all active:scale-95 disabled:opacity-60 shrink-0"
        >
          {phase === "idle" || phase === "finished" ? (
            <>
              <Zap className="w-4 h-4 fill-white" />
              <span>{phase === "finished" ? "Run Test Again" : "Start Speed Test"}</span>
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Testing {phase.toUpperCase()}...</span>
            </>
          )}
        </button>
      </div>

      {/* Main Gauge and Metrics Dashboard */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Dial Gauge */}
        <div className="lg:col-span-5 rounded-2xl bg-[#091326] border border-slate-700/60 p-6 shadow-xl flex flex-col items-center justify-center text-center relative overflow-hidden">
          <div className="absolute top-0 right-0 w-40 h-40 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

          {/* Speed Dial SVG */}
          <div className="relative w-52 h-52 flex items-center justify-center my-2">
            <svg className="w-full h-full -rotate-135" viewBox="0 0 100 100">
              {/* Background Arc */}
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke="#1e293b"
                strokeWidth="8"
                strokeDasharray="188.5"
                strokeDashoffset="0"
                strokeLinecap="round"
              />
              {/* Active Progress Arc */}
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke="url(#speed-gradient)"
                strokeWidth="8"
                strokeDasharray="188.5"
                strokeDashoffset={188.5 - (Math.min(currentSpeed, 100) / 100) * 188.5}
                strokeLinecap="round"
                className="transition-all duration-300 ease-out"
              />
              <defs>
                <linearGradient id="speed-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#06b6d4" />
                  <stop offset="50%" stopColor="#3b82f6" />
                  <stop offset="100%" stopColor="#a855f7" />
                </linearGradient>
              </defs>
            </svg>

            {/* Inner Gauge Text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
              <span className="text-4xl sm:text-5xl font-black text-white tracking-tighter">
                {currentSpeed.toFixed(1)}
              </span>
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-widest mt-1">
                Mbps
              </span>
              <span className="text-[10px] text-slate-400 capitalize mt-0.5">
                {phase === "download"
                  ? "Download Test"
                  : phase === "upload"
                  ? "Upload Test"
                  : phase === "finished"
                  ? "Benchmark Done"
                  : "Bandwidth Gauge"}
              </span>
            </div>
          </div>

          {/* Progress Bar & Status Text */}
          <div className="w-full mt-4 space-y-2">
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-cyan-500 to-blue-600 h-full rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-slate-300 font-medium">{statusMsg}</p>
          </div>
        </div>

        {/* Right Metric Cards */}
        <div className="lg:col-span-7 grid grid-cols-2 gap-4">
          {/* Download Speed Card */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Download
              </span>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center">
                <ArrowDown className="w-4 h-4" />
              </div>
            </div>
            <div className="my-4">
              <span className="text-3xl sm:text-4xl font-black text-white">
                {downloadSpeed !== null ? downloadSpeed.toFixed(1) : "--"}
              </span>
              <span className="text-xs font-bold text-cyan-400 ml-1.5 uppercase">Mbps</span>
            </div>
            <p className="text-[11px] text-slate-400">Throughput from server to device</p>
          </div>

          {/* Upload Speed Card */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Upload
              </span>
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                <ArrowUp className="w-4 h-4" />
              </div>
            </div>
            <div className="my-4">
              <span className="text-3xl sm:text-4xl font-black text-white">
                {uploadSpeed !== null ? uploadSpeed.toFixed(1) : "--"}
              </span>
              <span className="text-xs font-bold text-indigo-400 ml-1.5 uppercase">Mbps</span>
            </div>
            <p className="text-[11px] text-slate-400">Throughput from device to server</p>
          </div>

          {/* Ping Latency Card */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Ping (Latency)
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                <Zap className="w-4 h-4" />
              </div>
            </div>
            <div className="my-4">
              <span className="text-3xl sm:text-4xl font-black text-white">
                {ping !== null ? ping : "--"}
              </span>
              <span className="text-xs font-bold text-emerald-400 ml-1.5 uppercase">ms</span>
            </div>
            <p className="text-[11px] text-slate-400">Round-trip response time</p>
          </div>

          {/* Jitter Card */}
          <div className="rounded-2xl bg-[#091326] border border-slate-700/60 p-5 shadow-xl flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Jitter
              </span>
              <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <div className="my-4">
              <span className="text-3xl sm:text-4xl font-black text-white">
                {jitter !== null ? jitter : "--"}
              </span>
              <span className="text-xs font-bold text-amber-400 ml-1.5 uppercase">ms</span>
            </div>
            <p className="text-[11px] text-slate-400">Consistency of packet delivery</p>
          </div>
        </div>
      </div>

      {/* Network & Host Information Bar */}
      <div className="rounded-2xl bg-[#091326] border border-slate-800 p-4 shadow-xl flex flex-wrap items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-600/20 text-cyan-400 flex items-center justify-center">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">Client IP &amp; ISP</span>
            <span className="font-bold text-slate-200">
              {data.ip} · {data.connection.isp} ({data.connection.asn})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-600/20 text-purple-400 flex items-center justify-center">
            <Wifi className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">Location Endpoint</span>
            <span className="font-bold text-slate-200">
              {data.city}, {data.country} ({data.country_code})
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

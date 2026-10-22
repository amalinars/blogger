import Link from 'next/link';
import { ShieldCheck, Zap, Server, ArrowRight, Sparkles, CheckCircle2, Lock, Cpu } from 'lucide-react';
import { getAllPosts } from '@/lib/db';

export default function HomePage() {
  const posts = getAllPosts({ status: 'published' });
  const defaultSlug = posts[0]?.slug || 'lost-art-of-digital-craftsmanship';

  return (
    <div className="animate-fadeIn py-6 sm:py-12 max-w-4xl mx-auto px-4">
      {/* Editorial Masthead */}
      <div className="text-center space-y-4 mb-10">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full border border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-400 text-xs font-mono font-medium">
          <Sparkles className="w-3.5 h-3.5 animate-spin" />
          <span>Multi-Server Gateway Hub</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-serif font-bold tracking-tight" style={{ color: 'var(--text-main)' }}>
          Secure Dispatch Gateway
        </h1>
        <p className="text-sm sm:text-base font-serif italic max-w-xl mx-auto leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          Select an authenticated high-speed distribution node to initiate the 4-layer cryptographic handshake and retrieve your target package.
        </p>
      </div>

      {/* Two Dedicated Channel Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 my-8">
        {/* Channel 1: Server Alpha (Monetag Flow) */}
        <div
          className="p-6 sm:p-8 rounded-2xl border transition-all duration-300 hover:shadow-xl hover:-translate-y-1 relative flex flex-col justify-between group"
          style={{
            backgroundColor: 'var(--bg-card)',
            borderColor: 'var(--border-subtle)'
          }}
        >
          <div className="absolute top-4 right-4">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
          </div>

          <div className="space-y-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-600 dark:text-amber-400">
              <Zap className="w-6 h-6" />
            </div>

            <div>
              <span className="text-[11px] font-mono uppercase tracking-widest text-amber-600 dark:text-amber-400 font-bold">
                Channel Alpha
              </span>
              <h2 className="text-xl font-serif font-bold mt-1" style={{ color: 'var(--text-main)' }}>
                Direct Stream Node
              </h2>
            </div>

            <p className="text-xs sm:text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Optimized for ultra-fast throughput, instant cryptographic stream validation, and minimal edge latency.
            </p>

            <ul className="space-y-2 text-xs font-mono text-neutral-500 dark:text-neutral-400 pt-2 border-t border-dashed" style={{ borderColor: 'var(--border-subtle)' }}>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>Zero-Queue Instant Handoff</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>Direct Buffer Pre-computation</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>Global Anycast DNS Route</span>
              </li>
            </ul>
          </div>

          <div className="pt-6 mt-6">
            <Link
              href={`/read/${defaultSlug}?step=1`}
              className="w-full py-3.5 px-6 rounded-xl font-mono text-sm font-bold text-white transition-all transform group-hover:scale-[1.02] active:scale-[0.98] shadow-md flex items-center justify-center space-x-2 cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                boxShadow: '0 8px 20px -4px rgba(245, 158, 11, 0.4)'
              }}
            >
              <span>Connect via Node Alpha</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>

        {/* Channel 2: Server Beta (HilltopAds Flow) */}
        <div
          className="p-6 sm:p-8 rounded-2xl border transition-all duration-300 hover:shadow-xl hover:-translate-y-1 relative flex flex-col justify-between group"
          style={{
            backgroundColor: 'var(--bg-card)',
            borderColor: 'var(--border-subtle)'
          }}
        >
          <div className="absolute top-4 right-4">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
            </span>
          </div>

          <div className="space-y-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-600 dark:text-blue-400">
              <Server className="w-6 h-6" />
            </div>

            <div>
              <span className="text-[11px] font-mono uppercase tracking-widest text-blue-600 dark:text-blue-400 font-bold">
                Channel Beta
              </span>
              <h2 className="text-xl font-serif font-bold mt-1" style={{ color: 'var(--text-main)' }}>
                Encrypted Mirror Node
              </h2>
            </div>

            <p className="text-xs sm:text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Reinforced mirror network featuring isolated sandboxing, high-resilience bypass, and multi-zone verification.
            </p>

            <ul className="space-y-2 text-xs font-mono text-neutral-500 dark:text-neutral-400 pt-2 border-t border-dashed" style={{ borderColor: 'var(--border-subtle)' }}>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
                <span>Multi-Zone Redundant Uplink</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
                <span>Dynamic Packet Scrubbing</span>
              </li>
              <li className="flex items-center space-x-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
                <span>Hardened Firewall Traversal</span>
              </li>
            </ul>
          </div>

          <div className="pt-6 mt-6">
            <Link
              href={`/dispatch/${defaultSlug}?step=1`}
              className="w-full py-3.5 px-6 rounded-xl font-mono text-sm font-bold text-white transition-all transform group-hover:scale-[1.02] active:scale-[0.98] shadow-md flex items-center justify-center space-x-2 cursor-pointer"
              style={{
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                boxShadow: '0 8px 20px -4px rgba(59, 130, 246, 0.4)'
              }}
            >
              <span>Connect via Node Beta</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </div>

      {/* Security Assurance Badge */}
      <div
        className="p-5 rounded-2xl border text-center space-y-2 mt-8"
        style={{
          backgroundColor: 'var(--bg-subtle)',
          borderColor: 'var(--border-subtle)'
        }}
      >
        <div className="flex items-center justify-center space-x-2 text-xs font-mono font-semibold" style={{ color: 'var(--text-main)' }}>
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          <span>Cryptographically Verified Package Hub</span>
        </div>
        <p className="text-[11px] font-mono text-neutral-400 max-w-lg mx-auto">
          Both nodes guarantee safe routing to target payload (modapk.org) upon completion of the 4-layer inspection protocol.
        </p>
      </div>
    </div>
  );
}

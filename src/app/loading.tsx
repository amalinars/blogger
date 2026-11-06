export default function Loading() {
  return (
    <div className="min-h-screen bg-[#070c18] text-slate-100 flex flex-col animate-pulse">
      {/* Top Navbar Skeleton */}
      <div className="h-16 bg-[#091122] border-b border-slate-800 flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-slate-800" />
          <div className="h-5 w-32 bg-slate-800 rounded" />
        </div>
        <div className="h-9 w-64 bg-slate-800 rounded-lg hidden md:block" />
        <div className="h-8 w-24 bg-slate-800 rounded" />
      </div>

      {/* Ribbon Skeleton */}
      <div className="h-10 bg-blue-900/40 border-b border-blue-900/60" />

      {/* Top Banner Skeleton */}
      <div className="max-w-4xl mx-auto w-full my-4 px-4">
        <div className="h-20 bg-slate-800/60 rounded-xl" />
      </div>

      {/* Main Skeleton */}
      <main className="max-w-5xl mx-auto w-full px-4 space-y-6 py-4">
        <div className="h-36 bg-slate-800/40 rounded-2xl" />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 h-96 bg-slate-800/40 rounded-2xl" />
          <div className="lg:col-span-4 h-96 bg-slate-800/40 rounded-2xl" />
          <div className="lg:col-span-3 h-96 bg-slate-800/40 rounded-2xl" />
        </div>
      </main>
    </div>
  );
}

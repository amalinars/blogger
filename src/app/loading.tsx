export default function Loading() {
  return (
    <div
      className="relative min-h-[100dvh]"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="border-b border-line">
        <div className="mx-auto flex h-[73px] max-w-6xl items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="skeleton h-9 w-9 rounded-[11px]" />
            <div className="space-y-1.5">
              <div className="skeleton h-3 w-16 rounded-full" />
              <div className="skeleton h-2 w-20 rounded-full" />
            </div>
          </div>
          <div className="skeleton h-6 w-24 rounded-full" />
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl px-5 pb-16 pt-9 sm:px-8 sm:pt-12">
        <div className="grid gap-9 lg:grid-cols-[minmax(0,1.03fr)_minmax(0,0.97fr)] lg:items-start lg:gap-14">
          <div>
            <div className="skeleton h-7 w-40 rounded-full" />
            <div className="mt-6 space-y-3">
              <div className="skeleton h-12 w-full max-w-lg rounded-lg" />
              <div className="skeleton h-12 w-4/5 max-w-md rounded-lg" />
            </div>
            <div className="mt-5 space-y-2">
              <div className="skeleton h-4 w-full max-w-md rounded-full" />
              <div className="skeleton h-4 w-11/12 max-w-sm rounded-full" />
            </div>
            <div className="mt-7 grid max-w-md grid-cols-3 gap-4 border-y border-line py-4">
              <div className="skeleton h-9 w-12 rounded-md" />
              <div className="skeleton h-9 w-14 rounded-md" />
              <div className="skeleton h-9 w-8 rounded-md" />
            </div>
            <div className="mt-7 skeleton h-24 w-full max-w-md rounded-2xl" />
          </div>

          <div className="space-y-5">
            <div className="surface-card overflow-hidden">
              <div className="border-b border-line px-5 py-4">
                <div className="skeleton h-3 w-28 rounded-full" />
              </div>
              <div className="p-5 sm:p-6">
                <div className="skeleton h-6 w-2/3 rounded-lg" />
                <div className="mt-3 skeleton h-4 w-full rounded-full" />
                <div className="mt-2 skeleton h-4 w-4/5 rounded-full" />
                <div className="mt-5 skeleton aspect-[16/8] w-full rounded-2xl" />
                <div className="mt-5 flex items-center gap-3">
                  <div className="skeleton h-16 w-16 rounded-full" />
                  <div className="space-y-2">
                    <div className="skeleton h-3.5 w-32 rounded-full" />
                    <div className="skeleton h-3 w-44 rounded-full" />
                  </div>
                </div>
              </div>
            </div>

            <div className="surface-card overflow-hidden">
              <div className="border-b border-line px-5 py-4">
                <div className="skeleton h-3 w-24 rounded-full" />
              </div>
              <div className="p-5 sm:p-6">
                <div className="skeleton h-6 w-1/2 rounded-lg" />
                <div className="mt-3 skeleton h-4 w-full rounded-full" />
                <div className="mt-5 skeleton aspect-[16/8] w-full rounded-2xl" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <span className="sr-only">Loading gateway...</span>
    </div>
  );
}

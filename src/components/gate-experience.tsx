'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, ShieldCheck } from 'lucide-react';
import { BannerSlot } from '@/components/banner-ad-loader';
import { NativeAdSlot } from '@/components/native-ad-loader';
import {
  BANNER_LEADERBOARD,
  BANNER_MED_RECT,
  BANNER_SKYSCRAPER,
  getActiveSmartlink,
} from '@/lib/ads';
import { GateStep } from '@/components/gate-step';
import type { GateStepData, SiteDestination } from '@/lib/types';

type GateExperienceProps = {
  steps: GateStepData[];
  destination: SiteDestination;
};

function preferredScrollBehavior(): ScrollBehavior {
  if (typeof window === 'undefined') return 'auto';
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth';
}

export function GateExperience({ steps, destination }: GateExperienceProps) {
  const total = steps.length;
  const [completedCount, setCompletedCount] = useState(0);
  const [showDestination, setShowDestination] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const finalRef = useRef<HTMLElement | null>(null);

  const totalSeconds = steps.reduce((sum, step) => sum + step.delaySeconds, 0);
  const destinationProtocol = destination.url.startsWith('https:')
    ? 'HTTPS'
    : 'HTTP';

  useEffect(() => {
    if (completedCount === 0 || completedCount >= total) return;

    const timer = window.setTimeout(() => {
      const nextStep = document.getElementById(`step-${completedCount}`);
      if (!nextStep) return;

      nextStep.scrollIntoView({
        behavior: preferredScrollBehavior(),
        block: 'start',
      });
      nextStep.focus({ preventScroll: true });
    }, 260);

    return () => window.clearTimeout(timer);
  }, [completedCount, total]);

  useEffect(() => {
    if (!showDestination) return;

    const timer = window.setTimeout(() => {
      finalRef.current?.focus({ preventScroll: true });
      finalRef.current?.scrollIntoView({
        behavior: preferredScrollBehavior(),
        block: 'center',
      });
    }, 180);

    return () => window.clearTimeout(timer);
  }, [showDestination]);

  const smartlinkTriggered = useRef(false);

  function triggerSmartlink() {
    try {
      const url = getActiveSmartlink();
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch {
      // Ignored if popup blocked
    }
  }

  function handleStepComplete(stepIndex: number) {
    if (stepIndex !== completedCount || redirecting) return;

    // Trigger Smartlink on step continue click
    if (!smartlinkTriggered.current) {
      smartlinkTriggered.current = true;
      triggerSmartlink();
    }

    const next = Math.min(completedCount + 1, total);
    setCompletedCount(next);

    if (next >= total) {
      setShowDestination(true);
    }
  }

  function handleDestinationClick() {
    if (redirecting) return;
    setRedirecting(true);
    triggerSmartlink();
  }

  return (
    <div className="relative min-h-[100dvh]">
      <header className="relative z-10 border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <a
            href="#main"
            className="flex items-center gap-3 rounded-lg"
            aria-label="Gateway, back to top"
          >
            <span className="grid h-9 w-9 place-items-center rounded-[11px] bg-[var(--ink)] text-[var(--page)]">
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M5 19V9.5A4.5 4.5 0 0 1 9.5 5h5A4.5 4.5 0 0 1 19 9.5V19"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                />
                <path
                  d="M9 19v-5h6v5"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <span>
              <span className="block text-sm font-bold tracking-tight text-ink">
                Gateway
              </span>
              <span className="block font-code text-[9.5px] uppercase tracking-[0.18em] text-faint">
                route to destination
              </span>
            </span>
          </a>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1.5 text-[11px] font-medium text-muted sm:inline-flex">
              <span className="status-dot" aria-hidden="true" />
              Session active
            </span>
            <span className="font-code text-[10px] uppercase tracking-[0.16em] text-faint">
              {String(total).padStart(2, '0')} steps
            </span>
          </div>
        </div>
      </header>

      {/* Leaderboard: full-width below header */}
      <div className="relative z-10 border-b border-line bg-base">
        <div className="mx-auto max-w-6xl px-5 py-2 sm:px-8">
          <BannerSlot banner={BANNER_LEADERBOARD} />
        </div>
      </div>

      <main
        id="main"
        className="relative z-10 mx-auto w-full max-w-6xl px-5 pb-16 pt-9 sm:px-8 sm:pt-12"
      >
        <div className="grid gap-9 lg:grid-cols-[minmax(0,1.03fr)_minmax(0,0.97fr)] lg:items-start lg:gap-14">
          <div className="lg:sticky lg:top-10">
            <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1.5 font-code text-[10px] uppercase tracking-[0.16em] text-muted">
              <ShieldCheck size={13} strokeWidth={2} className="text-accent" aria-hidden="true" />
              Destination check
            </p>

            <h1 className="font-editorial mt-6 max-w-[13ch] text-balance text-[2.7rem] font-medium leading-[1.01] tracking-[-0.035em] text-ink sm:text-6xl lg:text-[4.1rem]">
              Three steps before you{' '}
              <em className="text-accent">continue.</em>
            </h1>

            <p className="mt-5 max-w-[45ch] text-[15px] leading-relaxed text-muted">
              This route makes sure you arrive at the right order page.
              Each step unlocks after a short pause, so no link gets skipped.
            </p>

            <dl className="mt-7 grid max-w-md grid-cols-3 divide-x divide-line border-y border-line">
              <div className="py-3 pl-0 pr-3">
                <dt className="font-code text-[9.5px] uppercase tracking-[0.15em] text-faint">
                  Steps
                </dt>
                <dd className="mt-1 font-code text-lg font-semibold text-ink">
                  {String(total).padStart(2, '0')}
                </dd>
              </div>
              <div className="px-3 py-3">
                <dt className="font-code text-[9.5px] uppercase tracking-[0.15em] text-faint">
                  Wait
                </dt>
                <dd className="mt-1 font-code text-lg font-semibold text-ink">
                  ≈{totalSeconds}
                  <span className="ml-1 text-[10px] font-normal text-muted">
                    sec
                  </span>
                </dd>
              </div>
              <div className="py-3 pl-3 pr-0">
                <dt className="font-code text-[9.5px] uppercase tracking-[0.15em] text-faint">
                  Destination
                </dt>
                <dd className="mt-1 font-code text-lg font-semibold text-ink">
                  1
                </dd>
              </div>
            </dl>

            <div className="mt-7">
              <div className="flex items-center justify-between gap-3">
                <span className="font-code text-[9.5px] uppercase tracking-[0.16em] text-faint">
                  Route progress
                </span>
                <span className="font-code text-[10px] text-muted">
                  {completedCount} / {total}
                </span>
              </div>
              <div
                className="mt-2.5 flex gap-1.5"
                role="progressbar"
                aria-label="Step progress"
                aria-valuemin={0}
                aria-valuemax={total}
                aria-valuenow={completedCount}
              >
                {steps.map((step, index) => (
                  <span
                    key={step.id}
                    className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${
                      index < completedCount
                        ? 'bg-accent'
                        : index === completedCount
                          ? 'bg-accent opacity-35'
                          : 'bg-surface-3'
                    }`}
                  />
                ))}
              </div>
            </div>

            <div className="mt-7 rounded-2xl border border-line bg-surface/70 p-4">
              <p className="font-code text-[9.5px] uppercase tracking-[0.16em] text-faint">
                Final destination
              </p>
              <p className="mt-1.5 truncate text-sm font-semibold text-ink">
                {destination.host}
              </p>
              <p className="mt-0.5 truncate font-code text-[11px] text-muted">
                {destination.path}
              </p>
            </div>

            <p className="mt-5 flex items-start gap-2 text-xs leading-relaxed text-faint">
              <ShieldCheck
                size={14}
                strokeWidth={2}
                className="mt-0.5 shrink-0 text-accent"
                aria-hidden="true"
              />
              No login, payment, or personal data is requested on this page.
            </p>

            {/* Sidebar banners */}
            <div className="mt-6 flex flex-col items-center gap-4">
              <BannerSlot banner={BANNER_MED_RECT} />
              <BannerSlot banner={BANNER_SKYSCRAPER} />
            </div>
          </div>

          <div className="min-w-0 space-y-5">
            {steps.map((step) => (
              <GateStep
                key={step.id}
                step={step}
                total={total}
                isActive={step.index === completedCount}
                isCompleted={step.index < completedCount}
                onComplete={() => handleStepComplete(step.index)}
              />
            ))}

            {/* Native Recommendation Ad Slot */}
            <NativeAdSlot className="mt-4" />

            {showDestination ? (
              <section
                ref={finalRef}
                id="destination"
                tabIndex={-1}
                aria-labelledby="destination-title"
                className="surface-card step-reveal step-shell overflow-hidden"
              >
                <div className="flex items-start gap-4 border-b border-line px-5 py-5 sm:px-6">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent text-accent-ink">
                    <Check size={20} strokeWidth={2.5} aria-hidden="true" />
                  </span>
                  <div>
                    <p className="font-code text-[9.5px] uppercase tracking-[0.16em] text-accent">
                      Route complete
                    </p>
                    <h2
                      id="destination-title"
                      className="font-editorial mt-1 text-balance text-2xl font-medium tracking-tight text-ink sm:text-[1.75rem]"
                    >
                      All steps complete.
                    </h2>
                    <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-muted">
                      The order page is ready. You will be redirected to the order
                      page.
                    </p>
                  </div>
                </div>

                <div className="p-5 sm:p-6">
                  <div className="surface-inset flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="font-code text-[9.5px] uppercase tracking-[0.16em] text-faint">
                        Destination
                      </p>
                      <p className="mt-1 truncate text-sm font-semibold text-ink">
                        {destination.host}
                      </p>
                      <p className="mt-0.5 truncate font-code text-[11px] text-muted">
                        {destination.path}
                      </p>
                    </div>
                    <span className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-full border border-line bg-surface px-2.5 py-1 font-code text-[9.5px] uppercase tracking-[0.12em] text-muted sm:self-center">
                      <ShieldCheck
                        size={12}
                        strokeWidth={2.2}
                        className="text-accent"
                        aria-hidden="true"
                      />
                      {destinationProtocol}
                    </span>
                  </div>

                  <a
                    href={destination.url}
                    onClick={handleDestinationClick}
                    className="btn-primary mt-4 w-full sm:w-auto"
                  >
                    Open order page
                    <ArrowUpRight size={16} strokeWidth={2.2} aria-hidden="true" />
                  </a>

                  <p className="mt-3 max-w-[46ch] text-xs leading-relaxed text-faint">
                    The link opens in the same tab. If it does not open, use the
                    button above once more.
                  </p>
                </div>
              </section>
            ) : null}
          </div>
        </div>
      </main>

      <footer className="relative z-10 border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-xs leading-relaxed text-faint">
            Gateway only forwards your visit. No account is created on this
            page.
          </p>
          <p className="font-code text-[9.5px] uppercase tracking-[0.14em] text-faint">
            Destination: {destination.host}
          </p>
        </div>
      </footer>

      {redirecting ? (
        <div
          className="redirect-overlay"
          role="status"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="surface-card step-reveal w-full max-w-sm p-6 text-center">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-line bg-surface-2">
              <span className="redirect-spinner" aria-hidden="true" />
            </span>
            <h2 className="font-editorial mt-4 text-2xl font-medium tracking-tight text-ink">
              Redirecting you now.
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              You will arrive at{' '}
              <span className="break-all font-code text-[11px] text-ink">
                {destination.host}
              </span>
              .
            </p>
            <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div className="redirect-progress" />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

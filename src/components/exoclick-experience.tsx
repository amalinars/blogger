'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, ShieldCheck, Sparkles } from 'lucide-react';
import {
  EXOCLICK_BANNER_ZONE_ID,
  EXOCLICK_INPAGE_PUSH_ZONE_ID,
  EXOCLICK_NATIVE_ZONE_ID,
  EXOCLICK_OUTSTREAM_ZONE_ID,
  EXOCLICK_POPUNDER_CODE,
  EXOCLICK_STICKY_ZONE_ID,
  resetExoClickPop,
  serveExoClick,
} from '@/lib/ads';
import { GateStep } from '@/components/gate-step';
import type { GateStepData, SiteDestination } from '@/lib/types';

type ExoClickExperienceProps = {
  slug: string;
  steps: GateStepData[];
  destination: SiteDestination;
};

function preferredScrollBehavior(): ScrollBehavior {
  if (typeof window === 'undefined') return 'auto';
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth';
}

export function ExoClickExperience({
  slug,
  steps,
  destination,
}: ExoClickExperienceProps) {
  const total = steps.length;
  const [completedCount, setCompletedCount] = useState(0);
  const [showDestination, setShowDestination] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const finalRef = useRef<HTMLElement | null>(null);
  const adsInitialized = useRef(false);

  useEffect(() => {
    if (adsInitialized.current) return;
    adsInitialized.current = true;

    // 1. Injeksi skrip Popunder ExoClick khusus halaman ini
    if (!document.getElementById('exoclick-dedicated-popunder')) {
      const popScript = document.createElement('script');
      popScript.id = 'exoclick-dedicated-popunder';
      popScript.type = 'application/javascript';
      popScript.text = EXOCLICK_POPUNDER_CODE;
      document.body.appendChild(popScript);
    }

    // 2. Load AdProvider skrip & tayangkan seluruh format ExoClick
    serveExoClick();
  }, []);

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

      const focusTarget = nextStep.querySelector<HTMLElement>(
        'button, a, [tabindex="0"]',
      );
      focusTarget?.focus({ preventScroll: true });
    }, 180);

    return () => window.clearTimeout(timer);
  }, [completedCount, total]);

  useEffect(() => {
    if (completedCount < total) return;

    setShowDestination(true);

    const timer = window.setTimeout(() => {
      const target = finalRef.current;
      if (!target) return;

      target.scrollIntoView({
        behavior: preferredScrollBehavior(),
        block: 'start',
      });

      const primary = target.querySelector<HTMLElement>('a.btn-primary');
      if (primary) {
        primary.focus({ preventScroll: true });
      } else {
        target.focus({ preventScroll: true });
      }
    }, 220);

    return () => window.clearTimeout(timer);
  }, [completedCount, total]);

  const handleStepComplete = (completedIndex: number) => {
    resetExoClickPop();
    setCompletedCount(completedIndex + 1);
  };

  const handleDestinationClick = () => {
    resetExoClickPop();
    setRedirecting(true);
  };

  return (
    <div className="relative min-h-screen bg-canvas text-ink flex flex-col justify-between selection:bg-accent/20">
      {/* 1. ExoClick In-Page Push Notification Tag (Top Right) */}
      <ins
        id="exoclick-inpage-push"
        className="eas6a97888e42"
        data-zoneid={String(EXOCLICK_INPAGE_PUSH_ZONE_ID)}
      />

      <header className="relative z-10 border-b border-line bg-surface/75 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface-2 font-code text-xs font-semibold text-accent shadow-sm">
              <Sparkles size={16} />
            </span>
            <div>
              <p className="font-editorial text-lg font-medium tracking-tight text-ink">
                Secure Content Handoff
              </p>
              <p className="font-code text-[10px] tracking-wider text-faint">
                ID: {slug.slice(0, 16)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 font-code text-[10px] font-medium text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Verified Fast Path
            </span>
          </div>
        </div>
      </header>

      {/* 2. Top Header Display Banner (Zone 6066244) */}
      <section className="mx-auto mt-4 w-full max-w-4xl px-4 flex justify-center">
        <div className="w-full overflow-hidden rounded-2xl border border-line bg-surface-raised p-2 text-center shadow-sm">
          <p className="font-code text-[9px] uppercase tracking-widest text-faint mb-1.5">
            Sponsor Announcement
          </p>
          <div className="min-h-[90px] flex items-center justify-center">
            <ins
              className="eas6a97888e2"
              data-zoneid={String(EXOCLICK_BANNER_ZONE_ID)}
            />
          </div>
        </div>
      </section>

      <main className="relative z-10 mx-auto w-full max-w-6xl px-5 py-8 sm:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_340px]">
          {/* Main Stepper Column */}
          <div className="min-w-0 space-y-6">
            {steps.map((step, idx) => (
              <Fragment key={step.id}>
                <GateStep
                  step={step}
                  total={total}
                  isActive={step.index === completedCount}
                  isCompleted={step.index < completedCount}
                  onComplete={() => handleStepComplete(step.index)}
                />

                {/* 3. Outstream Video Ad (Zone 6066272, Min Floor $0.20) Tepat di Bawah Step 1 */}
                {idx === 0 && (
                  <div className="exoclick-video-container my-4 overflow-hidden rounded-2xl border border-line bg-surface-raised p-4 shadow-sm transition-all">
                    <div className="mb-3 flex items-center justify-between border-b border-line pb-2.5">
                      <span className="font-code text-[10px] uppercase tracking-[0.16em] text-accent flex items-center gap-2 font-medium">
                        <span className="inline-block h-2 w-2 rounded-full bg-accent animate-ping" />
                        Featured Video Stream
                      </span>
                      <span className="rounded bg-surface-2 px-2 py-0.5 font-code text-[9px] uppercase tracking-wider text-muted">
                        Sponsored
                      </span>
                    </div>
                    <div className="min-h-[180px] w-full flex justify-center items-center overflow-hidden">
                      <ins
                        className="eas6a97888e37"
                        data-zoneid={String(EXOCLICK_OUTSTREAM_ZONE_ID)}
                      />
                    </div>
                  </div>
                )}
              </Fragment>
            ))}

            {/* 4. Native Recommendation Widget (Zone 6066238) */}
            <div className="exoclick-native-container mt-6 overflow-hidden rounded-2xl border border-line bg-surface-raised p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between border-b border-line pb-2.5">
                <span className="font-code text-[10.5px] uppercase tracking-[0.16em] text-faint font-medium">
                  Recommended For You
                </span>
                <span className="rounded bg-surface-2 px-2 py-0.5 font-code text-[9px] uppercase tracking-wider text-muted">
                  Partner Stories
                </span>
              </div>
              <div className="min-h-[160px] w-full flex justify-center">
                <ins
                  className="eas6a97888e20"
                  data-zoneid={String(EXOCLICK_NATIVE_ZONE_ID)}
                />
              </div>
            </div>

            {/* 5. Destination Reveal Card */}
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
                      All steps verified.
                    </h2>
                    <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-muted">
                      Your target link is ready. Click below to continue.
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
                    <ArrowUpRight
                      size={16}
                      strokeWidth={2.2}
                      aria-hidden="true"
                    />
                  </a>
                </div>
              </section>
            ) : null}
          </div>

          {/* Right Sidebar Column */}
          <aside className="space-y-6">
            <div className="surface-card p-5 sm:p-6">
              <p className="font-code text-[10px] uppercase tracking-[0.18em] text-accent">
                Verification Details
              </p>
              <h3 className="font-editorial mt-2 text-xl font-medium text-ink">
                Secure Link Gate
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Each step unlocks after a short pause, so no link gets skipped.
              </p>

              <dl className="mt-6 grid grid-cols-2 gap-3 border-t border-line pt-4">
                <div>
                  <dt className="font-code text-[9px] uppercase tracking-wider text-faint">
                    Steps
                  </dt>
                  <dd className="mt-1 font-code text-base font-semibold text-ink">
                    {completedCount} / {total}
                  </dd>
                </div>
                <div>
                  <dt className="font-code text-[9px] uppercase tracking-wider text-faint">
                    Estimated Wait
                  </dt>
                  <dd className="mt-1 font-code text-base font-semibold text-ink">
                    ≈{totalSeconds}s
                  </dd>
                </div>
              </dl>
            </div>

            {/* Sidebar Display Banner (Zone 6066244) */}
            <div className="overflow-hidden rounded-2xl border border-line bg-surface-raised p-3 text-center shadow-sm">
              <p className="font-code text-[9px] uppercase tracking-widest text-faint mb-2">
                Featured Partner
              </p>
              <div className="min-h-[250px] flex items-center justify-center">
                <ins
                  className="eas6a97888e2"
                  data-zoneid={String(EXOCLICK_BANNER_ZONE_ID)}
                />
              </div>
            </div>
          </aside>
        </div>
      </main>

      {/* 6. ExoClick Sticky Footer Banner (Zone 6066266) */}
      <div
        id="exoclick-sticky-wrapper"
        className="exoclick-sticky-container fixed bottom-0 left-0 right-0 z-40 flex justify-center bg-surface/90 backdrop-blur-md border-t border-line py-1.5 shadow-lg"
      >
        <ins
          id="exoclick-sticky-banner"
          className="eas6a97888e17"
          data-zoneid={String(EXOCLICK_STICKY_ZONE_ID)}
        />
      </div>

      <footer className="relative z-10 border-t border-line pb-20">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-xs text-faint">
            Fast Handoff Gateway. Content verified through authenticated provider.
          </p>
          <p className="font-code text-[9.5px] uppercase tracking-widest text-faint">
            Session Target: {destination.host}
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
            <p className="mt-1 text-sm text-muted">
              Forwarding to destination page...
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, ExternalLink, Newspaper, ShieldCheck } from 'lucide-react';
import { MONETAG_DIRECT_LINK, MONETAG_MULTITAG_SRC, MONETAG_MULTITAG_ZONE } from '@/lib/ads';
import { GateStep } from '@/components/gate-step';
import type { GateStepData, SiteDestination } from '@/lib/types';

type MonetagExperienceProps = {
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

export function MonetagExperience({
  slug,
  steps,
  destination,
}: MonetagExperienceProps) {
  const total = steps.length;
  const [completedCount, setCompletedCount] = useState(0);
  const [showDestination, setShowDestination] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const finalRef = useRef<HTMLElement | null>(null);
  const adsInitialized = useRef(false);

  useEffect(() => {
    if (adsInitialized.current) return;
    adsInitialized.current = true;

    // Load Monetag MultiTag script khusus halaman /m/
    if (!document.getElementById('monetag-dedicated-tag')) {
      const script = document.createElement('script');
      script.id = 'monetag-dedicated-tag';
      script.src = MONETAG_MULTITAG_SRC;
      script.dataset.zone = MONETAG_MULTITAG_ZONE;
      script.dataset.cfasync = 'false';
      script.async = true;
      document.head.appendChild(script);
    }
  }, []);

  const totalSeconds = steps.reduce((sum, step) => sum + step.delaySeconds, 0);

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
    setCompletedCount(completedIndex + 1);
  };

  const handleDestinationClick = () => {
    setRedirecting(true);
  };

  return (
    <div className="relative min-h-screen bg-canvas text-ink flex flex-col justify-between selection:bg-accent/20">
      <header className="relative z-10 border-b border-line bg-surface/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface-2 font-code text-xs font-semibold text-accent shadow-sm">
              <Newspaper size={16} />
            </span>
            <div>
              <p className="font-editorial text-lg font-medium tracking-tight text-ink">
                Curated News Reader
              </p>
              <p className="font-code text-[10px] tracking-wider text-faint">
                Portal ID: {slug.slice(0, 16)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 font-code text-[10px] font-medium text-sky-400">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
              Live Feed
            </span>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-5xl px-5 py-8 sm:px-8">
        <div className="min-w-0 space-y-6">
          {steps.map((step) => (
            <Fragment key={step.id}>
              <GateStep
                step={step}
                total={total}
                isActive={step.index === completedCount}
                isCompleted={step.index < completedCount}
                onComplete={() => handleStepComplete(step.index)}
              />
            </Fragment>
          ))}

          {/* Destination Reveal Card */}
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
                    Articles verified.
                  </h2>
                  <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-muted">
                    Your reading pathway is complete. Proceed to target destination.
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
                    Secured
                  </span>
                </div>

                <div className="mt-5 flex flex-wrap gap-3">
                  <a
                    href={destination.url}
                    onClick={handleDestinationClick}
                    className="btn-primary flex-1 sm:flex-initial"
                  >
                    Continue to destination
                    <ArrowUpRight
                      size={16}
                      strokeWidth={2.2}
                      aria-hidden="true"
                    />
                  </a>

                  {/* Direct Link Trigger Action ($0.90 CPM) */}
                  <a
                    href={MONETAG_DIRECT_LINK}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary flex items-center justify-center gap-2 px-4 py-2.5 font-code text-xs font-medium text-ink/80 hover:text-ink"
                  >
                    <span>Partner Resource</span>
                    <ExternalLink size={14} className="text-muted" />
                  </a>
                </div>
              </div>
            </section>
          ) : null}
        </div>
      </main>

      <footer className="relative z-10 border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-xs text-faint">
            Fast verification portal. Content aggregated from verified news wires.
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

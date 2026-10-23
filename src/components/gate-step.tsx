'use client';

import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { ArrowRight, Check, Clock } from 'lucide-react';
import type { GateStepData } from '@/lib/types';

type GateStepProps = {
  step: GateStepData;
  total: number;
  isActive: boolean;
  isCompleted: boolean;
  onComplete: () => void;
};

function statusLabel(isActive: boolean, isCompleted: boolean, isReady: boolean) {
  if (isCompleted) return 'Done';
  if (!isActive) return 'Locked';
  return isReady ? 'Ready' : 'Waiting';
}

export function GateStep({
  step,
  total,
  isActive,
  isCompleted,
  onComplete,
}: GateStepProps) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [remaining, setRemaining] = useState(step.delaySeconds);

  const isReady = remaining <= 0;
  const canContinue = isActive && !isCompleted && isReady;
  const progress =
    step.delaySeconds > 0
      ? Math.min(100, Math.max(0, ((step.delaySeconds - remaining) / step.delaySeconds) * 100))
      : 100;
  const label = statusLabel(isActive, isCompleted, isReady);

  useEffect(() => {
    if (!isActive || isCompleted) return;

    const node = sectionRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        setIsVisible(entries[0]?.isIntersecting ?? false);
      },
      { threshold: 0.25, rootMargin: '-8% 0px -12% 0px' },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [isActive, isCompleted]);

  useEffect(() => {
    if (!isActive || isCompleted || !isVisible || isReady) return;

    const timer = window.setInterval(() => {
      setRemaining((previous) => {
        if (previous <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return previous - 1;
      });
    }, 1000);

    return () => window.clearInterval(timer);
  }, [isActive, isCompleted, isVisible, isReady]);

  return (
    <section
      ref={sectionRef}
      id={`step-${step.index}`}
      tabIndex={-1}
      aria-current={isActive ? 'step' : undefined}
      aria-labelledby={`step-title-${step.index}`}
      className="step-shell step-reveal"
    >
      <div className="surface-card overflow-hidden">
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3.5 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="font-code text-[11px] text-faint">
              STEP {String(step.index + 1).padStart(2, '0')}
            </span>
            <span className="h-px w-5 bg-[var(--line-strong)]" aria-hidden="true" />
            <span className="font-code text-[11px] text-faint">
              {String(step.index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
            </span>
          </div>

          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              isCompleted || (isActive && isReady)
                ? 'bg-accent-soft text-accent-soft-ink'
                : 'bg-surface-2 text-muted'
            }`}
          >
            {isCompleted ? (
              <Check size={12} strokeWidth={2.6} aria-hidden="true" />
            ) : isActive ? (
              <span className="status-dot" aria-hidden="true" />
            ) : (
              <Clock size={12} strokeWidth={2} aria-hidden="true" />
            )}
            {label}
          </span>
        </div>

        <div className="p-5 sm:p-6">
          <h2
            id={`step-title-${step.index}`}
            className="text-balance text-xl font-semibold tracking-tight text-ink sm:text-2xl"
          >
            {step.title}
          </h2>
          <p className="mt-2 max-w-[52ch] text-sm leading-relaxed text-muted">
            {step.description}
          </p>

          <div className="mt-5 overflow-hidden rounded-2xl border border-line bg-surface-raised">
            <div className="article-cover relative aspect-[16/8] min-h-[178px]">
              {step.article.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={step.article.imageUrl}
                  alt=""
                  loading={step.index === 0 ? 'eager' : 'lazy'}
                  decoding="async"
                  referrerPolicy="no-referrer"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              ) : null}

              <div
                className="absolute inset-0 bg-gradient-to-t from-black/88 via-black/30 to-black/10"
                aria-hidden="true"
              />

              <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-3 p-4">
                <span className="rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-semibold text-white backdrop-blur-sm">
                  {step.article.categoryLabel}
                </span>
                <span className="rounded-full bg-black/45 px-2.5 py-1 font-code text-[10px] text-white/85 backdrop-blur-sm">
                  {step.article.source}
                </span>
              </div>

              <div className="absolute inset-x-0 bottom-0 p-4 sm:p-5">
                <h3 className="font-editorial line-clamp-3 text-balance text-[1.4rem] font-medium leading-[1.15] text-white sm:text-[1.65rem]">
                  {step.article.title}
                </h3>
              </div>
            </div>

            <div className="p-4 sm:p-5">
              <p className="text-sm leading-relaxed text-muted">
                {step.article.snippet}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-code text-[10.5px] text-faint">
                <span>{step.article.source}</span>
                {step.article.publishedLabel ? (
                  <>
                    <span aria-hidden="true">/</span>
                    <span>{step.article.publishedLabel}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          {step.related.length > 0 ? (
            <div className="mt-5 border-t border-line pt-4">
              <p className="text-xs font-semibold text-ink">More from this channel</p>
              <ul className="mt-1 divide-y divide-line">
                {step.related.map((item) => (
                  <li key={item.id} className="py-2.5">
                    <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">
                      {item.title}
                    </p>
                    {item.publishedLabel ? (
                      <p className="mt-1 font-code text-[10px] text-faint">
                        {item.publishedLabel}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-6 border-t border-line pt-5">
            {isCompleted ? (
              <div className="flex items-center gap-3 rounded-2xl bg-accent-soft px-4 py-3.5 text-accent-soft-ink">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent text-accent-ink">
                  <Check size={16} strokeWidth={2.6} aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold">Step complete</p>
                  <p className="mt-0.5 text-xs text-accent-soft-ink/80">
                    Link unlocked. Continue to the next section.
                  </p>
                </div>
              </div>
            ) : !isActive ? (
              <div className="flex items-center gap-3 rounded-2xl border border-dashed border-line-strong bg-surface-2 px-4 py-3.5">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-line-strong text-faint">
                  <Clock size={15} strokeWidth={2} aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">
                    Waiting for the previous step
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    The button unlocks after the previous step is complete.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="countdown-ring"
                    style={{ '--progress': progress } as CSSProperties}
                    aria-hidden="true"
                  >
                    <div className="text-center">
                      <span className="block font-code text-lg font-semibold leading-none text-ink">
                        {remaining}
                      </span>
                      <span className="mt-0.5 block text-[9px] uppercase tracking-[0.14em] text-faint">
                        sec
                      </span>
                    </div>
                  </div>

                  <div>
                    <p className="text-sm font-semibold text-ink">
                      {isReady ? 'Ready to continue' : 'Preparing your link'}
                    </p>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted">
                      {isReady
                        ? 'Click the button to unlock the next step.'
                        : `Wait ${remaining} ${remaining === 1 ? 'second' : 'seconds'}.`}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  className="btn-primary w-full sm:w-auto"
                  disabled={!canContinue}
                  onClick={onComplete}
                >
                  {step.index === total - 1 ? 'Open order page' : 'Continue'}
                  <ArrowRight size={16} strokeWidth={2.2} aria-hidden="true" />
                </button>
              </div>
            )}

            <span className="sr-only" role="status" aria-live="polite">
              {canContinue ? 'Step ready. The continue button is now active.' : ''}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

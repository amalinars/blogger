'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  ExternalLink,
  Layers,
  Newspaper,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';
import { HILLTOPADS_CONFIG } from '@/lib/ads';
import { GateStep } from '@/components/gate-step';
import type { GateStepData, SiteDestination } from '@/lib/types';

type HilltopExperienceProps = {
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

export function HilltopExperience({
  slug,
  steps,
  destination,
}: HilltopExperienceProps) {
  const total = steps.length;
  const [completedCount, setCompletedCount] = useState(0);
  const [showDestination, setShowDestination] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const finalRef = useRef<HTMLElement | null>(null);
  const adsInitialized = useRef(false);
  const bannerContainerRef = useRef<HTMLDivElement | null>(null);
  const sidebarBannerRef = useRef<HTMLDivElement | null>(null);
  const inpagePushRef = useRef<HTMLDivElement | null>(null);
  const videoSliderRef = useRef<HTMLDivElement | null>(null);

  // Injeksi script iklan HilltopAds (Popunder, Banner, In-Page Push, Video Slider)
  useEffect(() => {
    if (adsInitialized.current) return;
    adsInitialized.current = true;

    // 1. Popunder Script
    if (HILLTOPADS_CONFIG.popunder.scriptSrc && !document.getElementById('hilltop-popunder')) {
      const popScript = document.createElement('script');
      popScript.id = 'hilltop-popunder';
      (popScript as any).settings = {};
      popScript.async = true;
      popScript.src = HILLTOPADS_CONFIG.popunder.scriptSrc;
      popScript.referrerPolicy = 'no-referrer-when-downgrade';
      document.head.appendChild(popScript);
    }

    // 2. MultiTag (Banner 300x250 & Display) Script
    if (HILLTOPADS_CONFIG.multitag.scriptSrc && !document.getElementById('hilltop-multitag')) {
      const multiScript = document.createElement('script');
      multiScript.id = 'hilltop-multitag';
      (multiScript as any).settings = {};
      multiScript.async = true;
      multiScript.src = HILLTOPADS_CONFIG.multitag.scriptSrc;
      multiScript.referrerPolicy = 'no-referrer-when-downgrade';
      document.head.appendChild(multiScript);
    }

    if (HILLTOPADS_CONFIG.banner_300x250.scriptSrc && bannerContainerRef.current) {
      const bannerScript = document.createElement('script');
      (bannerScript as any).settings = {};
      bannerScript.async = true;
      bannerScript.src = HILLTOPADS_CONFIG.banner_300x250.scriptSrc;
      bannerScript.referrerPolicy = 'no-referrer-when-downgrade';
      bannerContainerRef.current.appendChild(bannerScript);
    }

    // 3. In-Page Push Script
    if (HILLTOPADS_CONFIG.inpage_push.scriptSrc && !document.getElementById('hilltop-inpage-push-script')) {
      const pushScript = document.createElement('script');
      pushScript.id = 'hilltop-inpage-push-script';
      (pushScript as any).settings = {};
      pushScript.async = true;
      pushScript.src = HILLTOPADS_CONFIG.inpage_push.scriptSrc;
      pushScript.referrerPolicy = 'no-referrer-when-downgrade';
      document.head.appendChild(pushScript);
    }

    // 4. Video Slider Script
    if (HILLTOPADS_CONFIG.video_slider.scriptSrc && videoSliderRef.current) {
      const videoScript = document.createElement('script');
      videoScript.async = true;
      videoScript.src = HILLTOPADS_CONFIG.video_slider.scriptSrc;
      videoScript.referrerPolicy = 'no-referrer-when-downgrade';
      videoSliderRef.current.appendChild(videoScript);
    }
  }, []);

  const totalSeconds = steps.reduce((sum, step) => sum + step.delaySeconds, 0);

  // Auto-scroll ke step berikutnya saat step selesai
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

  // Reveal Destination saat seluruh step selesai
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
      {/* Container In-Page Push Floating (HilltopAds Zone) */}
      <div
        ref={inpagePushRef}
        id="hilltop-inpage-push"
        data-ad-zone="hilltopads-inpage-push"
        className="fixed top-3 right-3 z-50 pointer-events-auto"
      />

      {/* Container Video Slider (HilltopAds Zone) */}
      <div
        ref={videoSliderRef}
        id="hilltop-video-slider"
        data-ad-zone="hilltopads-video-slider"
        className="fixed bottom-4 right-4 z-40"
      />

      {/* Top Header */}
      <header className="relative z-10 border-b border-line bg-surface/75 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-surface-2 font-code text-xs font-semibold text-accent shadow-sm">
              <Sparkles size={16} />
            </span>
            <div>
              <p className="font-editorial text-lg font-medium tracking-tight text-ink">
                Secure Content Gateway
              </p>
              <p className="font-code text-[10px] tracking-wider text-faint">
                ROUTE-H : {slug.slice(0, 16)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 font-code text-[10px] font-medium text-sky-400">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
              Hilltop Ultra Fast
            </span>
          </div>
        </div>
      </header>

      {/* Top Sponsored Announcement / Banner Slot */}
      <section className="mx-auto mt-4 w-full max-w-4xl px-4 flex justify-center">
        <div className="w-full overflow-hidden rounded-2xl border border-line bg-surface-raised p-3 text-center shadow-sm">
          <p className="font-code text-[9px] uppercase tracking-widest text-faint mb-2">
            Sponsored Announcement
          </p>
          <div
            ref={bannerContainerRef}
            id="hilltop-banner-top"
            data-ad-zone="hilltopads-banner-300x250"
            className="min-h-[100px] flex items-center justify-center overflow-hidden"
          >
            <div className="flex flex-col items-center justify-center p-3 text-xs text-faint font-code">
              <span>[ HilltopAds MultiTag Placement ]</span>
              <span className="text-[10px] opacity-60">Popunder &bull; Banner 300x250 &bull; In-Page Push</span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Layout */}
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

                {/* Banner 300x250 di antara step (Memaksimalkan Viewability) */}
                {idx === 0 && (
                  <div className="my-4 overflow-hidden rounded-2xl border border-line bg-surface-raised p-4 shadow-sm transition-all text-center">
                    <div className="mb-2 flex items-center justify-between border-b border-line pb-2">
                      <span className="font-code text-[10px] uppercase tracking-[0.16em] text-accent font-medium">
                        Featured Sponsor
                      </span>
                      <span className="rounded bg-surface-2 px-2 py-0.5 font-code text-[9px] uppercase tracking-wider text-muted">
                        Ad
                      </span>
                    </div>
                    <div
                      id="hilltop-incontent-banner"
                      data-ad-zone="hilltopads-incontent-300x250"
                      className="min-h-[250px] w-full flex justify-center items-center overflow-hidden"
                    >
                      <div className="p-6 border border-dashed border-line rounded-xl text-center text-faint font-code text-xs">
                        HilltopAds 300x250 In-Content Zone
                      </div>
                    </div>
                  </div>
                )}
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
                      className="mt-0.5 font-editorial text-2xl font-medium tracking-tight text-ink sm:text-3xl"
                    >
                      Your content is ready
                    </h2>
                  </div>
                </div>

                <div className="space-y-5 px-5 py-6 sm:px-6">
                  <p className="font-sans text-sm leading-relaxed text-muted">
                    Verification successful. Click the secure link below to proceed to your requested article.
                  </p>

                  <div className="rounded-xl border border-line bg-surface-raised p-4">
                    <p className="font-code text-[9.5px] uppercase tracking-wider text-faint">
                      Target Destination
                    </p>
                    <p className="mt-1 font-mono text-xs break-all text-ink">
                      {destination.url}
                    </p>
                  </div>

                  <div className="pt-2">
                    <a
                      href={destination.url}
                      onClick={handleDestinationClick}
                      className="btn-primary flex w-full items-center justify-center gap-2 py-3.5 text-sm font-medium tracking-wide shadow-md transition-all hover:shadow-lg"
                    >
                      {redirecting ? (
                        <span>Redirecting safely...</span>
                      ) : (
                        <>
                          <span>Proceed to Target Content</span>
                          <ExternalLink size={16} />
                        </>
                      )}
                    </a>
                  </div>
                </div>
              </section>
            ) : (
              <div className="rounded-2xl border border-dashed border-line p-5 text-center font-code text-xs text-faint">
                Complete the step above to unlock the destination link.
              </div>
            )}
          </div>

          {/* Sticky Sidebar Column */}
          <aside className="space-y-6">
            <div className="sticky top-6 space-y-6">
              {/* Sidebar Ad Placement (300x250) */}
              <div className="overflow-hidden rounded-2xl border border-line bg-surface-raised p-4 shadow-sm text-center">
                <p className="font-code text-[9px] uppercase tracking-widest text-faint mb-3">
                  Sponsor Showcase
                </p>
                <div
                  ref={sidebarBannerRef}
                  id="hilltop-sidebar-banner"
                  data-ad-zone="hilltopads-sidebar-300x250"
                  className="min-h-[250px] w-full flex items-center justify-center overflow-hidden"
                >
                  <div className="p-4 border border-dashed border-line rounded-xl text-center text-faint font-code text-xs">
                    HilltopAds 300x250 Sidebar Banner
                  </div>
                </div>
              </div>

              {/* Progress Summary Card */}
              <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <ShieldCheck size={18} className="text-accent" />
                  <h3 className="font-editorial text-base font-medium text-ink">
                    Handoff Verification
                  </h3>
                </div>
                <div className="space-y-3 font-code text-xs text-muted">
                  <div className="flex justify-between border-b border-line pb-2">
                    <span>Provider</span>
                    <span className="font-medium text-sky-400">HilltopAds</span>
                  </div>
                  <div className="flex justify-between border-b border-line pb-2">
                    <span>Progress</span>
                    <span>{completedCount} / {total} Steps</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Target</span>
                    <span className="truncate max-w-[150px] text-faint">{destination.host}</span>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-line bg-surface/50 py-6 text-center text-xs text-faint font-code">
        <p>&copy; {new Date().getFullYear()} Content Distribution Network. Secured by HilltopAds Verified Gateway.</p>
      </footer>
    </div>
  );
}

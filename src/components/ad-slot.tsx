import Script from 'next/script';
import { ADSTERRA } from '@/lib/ads';

export function AdSlot() {
  return (
    <section
      aria-label="Advertisement"
      className="mt-10 border-t border-line pt-5"
    >
      <p className="font-code text-[9.5px] uppercase tracking-[0.16em] text-faint">
        Advertisement
      </p>
      <div
        id={ADSTERRA.nativeBannerContainerId}
        className="mt-3 min-h-[110px] w-full overflow-hidden rounded-2xl border border-line bg-surface/60"
      />
      <Script
        id="adsterra-native-banner"
        src={ADSTERRA.nativeBannerSrc}
        strategy="afterInteractive"
        data-cfasync="false"
      />
    </section>
  );
}

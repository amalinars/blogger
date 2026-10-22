'use client';

import { useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { MONETAG_CONFIG, HILLTOPADS_CONFIG } from '@/lib/ad-config';

export function SmartPopunder() {
  const searchParams = useSearchParams();
  const stepParam = searchParams.get('step');
  const step = Math.min(4, Math.max(1, parseInt(stepParam || '1', 10) || 1));
  const activeScriptRef = useRef<HTMLScriptElement | null>(null);

  useEffect(() => {
    // Odd steps (1, 3) -> Monetag Popunder
    // Even steps (2, 4) -> HilltopAds Popunder
    const isHilltop = step % 2 === 0;

    // Cleanup existing injected script
    if (activeScriptRef.current && activeScriptRef.current.parentNode) {
      activeScriptRef.current.parentNode.removeChild(activeScriptRef.current);
      activeScriptRef.current = null;
    }

    const script = document.createElement('script');
    script.async = true;

    if (isHilltop) {
      // HilltopAds Popunder
      script.src = HILLTOPADS_CONFIG.popunder.scriptSrc;
      script.referrerPolicy = 'no-referrer-when-downgrade';
    } else {
      // Monetag Popunder
      script.src = MONETAG_CONFIG.zones.popunder.scriptSrc;
      script.dataset.zone = MONETAG_CONFIG.zones.popunder.zone;
      script.setAttribute('data-cfasync', 'false');
    }

    document.head.appendChild(script);
    activeScriptRef.current = script;

    return () => {
      if (activeScriptRef.current && activeScriptRef.current.parentNode) {
        activeScriptRef.current.parentNode.removeChild(activeScriptRef.current);
        activeScriptRef.current = null;
      }
    };
  }, [step]);

  return null;
}

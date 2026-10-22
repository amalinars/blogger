'use client';

import { useEffect, useRef } from 'react';
import { MONETAG_CONFIG } from '@/lib/ad-config';

export function MonetagScripts() {
  const popunderRef = useRef<HTMLScriptElement | null>(null);
  const ippRef = useRef<HTMLScriptElement | null>(null);
  const vignetteRef = useRef<HTMLScriptElement | null>(null);

  useEffect(() => {
    // 1. Monetag Popunder
    if (MONETAG_CONFIG.zones.popunder.scriptSrc) {
      const sPop = document.createElement('script');
      sPop.src = MONETAG_CONFIG.zones.popunder.scriptSrc;
      sPop.dataset.zone = MONETAG_CONFIG.zones.popunder.zone;
      sPop.setAttribute('data-cfasync', 'false');
      sPop.async = true;
      document.head.appendChild(sPop);
      popunderRef.current = sPop;
    }

    // 2. Monetag In-Page Push (IPP)
    if (MONETAG_CONFIG.zones.inPagePush.scriptSrc) {
      const sIpp = document.createElement('script');
      sIpp.src = MONETAG_CONFIG.zones.inPagePush.scriptSrc;
      sIpp.dataset.zone = MONETAG_CONFIG.zones.inPagePush.zone;
      sIpp.setAttribute('data-cfasync', 'false');
      sIpp.async = true;
      document.head.appendChild(sIpp);
      ippRef.current = sIpp;
    }

    // 3. Monetag Vignette (Interstitial)
    if (MONETAG_CONFIG.zones.vignette.scriptSrc) {
      const sVignette = document.createElement('script');
      sVignette.src = MONETAG_CONFIG.zones.vignette.scriptSrc;
      sVignette.dataset.zone = MONETAG_CONFIG.zones.vignette.zone;
      sVignette.setAttribute('data-cfasync', 'false');
      sVignette.async = true;
      document.head.appendChild(sVignette);
      vignetteRef.current = sVignette;
    }

    return () => {
      [popunderRef, ippRef, vignetteRef].forEach((ref) => {
        if (ref.current && ref.current.parentNode) {
          ref.current.parentNode.removeChild(ref.current);
          ref.current = null;
        }
      });
    };
  }, []);

  return null;
}

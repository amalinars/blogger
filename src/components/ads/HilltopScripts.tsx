'use client';

import { useEffect, useRef } from 'react';
import { HILLTOPADS_CONFIG } from '@/lib/ad-config';

export function HilltopScripts() {
  const popunderRef = useRef<HTMLScriptElement | null>(null);

  useEffect(() => {
    // HilltopAds Popunder
    if (HILLTOPADS_CONFIG.popunder.scriptSrc) {
      const sPop = document.createElement('script');
      sPop.src = HILLTOPADS_CONFIG.popunder.scriptSrc;
      sPop.referrerPolicy = 'no-referrer-when-downgrade';
      sPop.async = true;
      document.head.appendChild(sPop);
      popunderRef.current = sPop;
    }

    return () => {
      if (popunderRef.current && popunderRef.current.parentNode) {
        popunderRef.current.parentNode.removeChild(popunderRef.current);
        popunderRef.current = null;
      }
    };
  }, []);

  return null;
}

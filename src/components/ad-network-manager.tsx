'use client';

import { useEffect, useRef } from 'react';
import {
  getAdProvider,
  MONETAG_MULTITAG_SRC,
  MONETAG_MULTITAG_ZONE,
  EXOCLICK_POPUNDER_CODE,
  EXOCLICK_INPAGE_PUSH_ZONE_ID,
  EXOCLICK_STICKY_ZONE_ID,
  serveExoClick,
  HILLTOPADS_CONFIG,
} from '@/lib/ads';

export function AdNetworkManager() {
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    if (
      typeof window !== 'undefined' &&
      (window.location.pathname.startsWith('/v/') ||
        window.location.pathname.startsWith('/m/') ||
        window.location.pathname.startsWith('/h/'))
    ) {
      return;
    }

    const provider = getAdProvider();

    if (provider === 'exoclick') {
      // 1. Load ExoClick Popunder script
      if (!document.getElementById('exoclick-popunder')) {
        const exoScript = document.createElement('script');
        exoScript.id = 'exoclick-popunder';
        exoScript.type = 'application/javascript';
        exoScript.text = EXOCLICK_POPUNDER_CODE;
        document.body.appendChild(exoScript);
      }

      // 2. Load ExoClick In-Page Push Notification
      if (!document.getElementById('exoclick-inpage-push')) {
        const pushIns = document.createElement('ins');
        pushIns.id = 'exoclick-inpage-push';
        pushIns.className = 'eas6a97888e42';
        pushIns.setAttribute('data-zoneid', String(EXOCLICK_INPAGE_PUSH_ZONE_ID));
        document.body.appendChild(pushIns);
      }

      // 3. Load ExoClick Sticky Banner (Footer)
      if (!document.getElementById('exoclick-sticky-wrapper')) {
        const stickyWrapper = document.createElement('div');
        stickyWrapper.id = 'exoclick-sticky-wrapper';
        stickyWrapper.className = 'exoclick-sticky-container';

        const stickyIns = document.createElement('ins');
        stickyIns.id = 'exoclick-sticky-banner';
        stickyIns.className = 'eas6a97888e17';
        stickyIns.setAttribute('data-zoneid', String(EXOCLICK_STICKY_ZONE_ID));
        stickyWrapper.appendChild(stickyIns);
        document.body.appendChild(stickyWrapper);
      }

      // 4. Load ExoClick AdProvider Script & serve all widgets
      serveExoClick();
    } else if (provider === 'hilltop') {
      // 1. Load HilltopAds Popunder script
      if (!document.getElementById('hilltop-popunder-global') && HILLTOPADS_CONFIG.popunder.scriptSrc) {
        const script = document.createElement('script');
        script.id = 'hilltop-popunder-global';
        (script as any).settings = {};
        script.src = HILLTOPADS_CONFIG.popunder.scriptSrc;
        script.async = true;
        script.referrerPolicy = 'no-referrer-when-downgrade';
        document.head.appendChild(script);
      }

      // 2. Load HilltopAds MultiTag script
      if (!document.getElementById('hilltop-multitag-global') && HILLTOPADS_CONFIG.multitag.scriptSrc) {
        const script = document.createElement('script');
        script.id = 'hilltop-multitag-global';
        (script as any).settings = {};
        script.src = HILLTOPADS_CONFIG.multitag.scriptSrc;
        script.async = true;
        script.referrerPolicy = 'no-referrer-when-downgrade';
        document.head.appendChild(script);
      }

      // 3. Load HilltopAds In-Page Push script
      if (!document.getElementById('hilltop-inpage-push-global') && HILLTOPADS_CONFIG.inpage_push.scriptSrc) {
        const script = document.createElement('script');
        script.id = 'hilltop-inpage-push-global';
        (script as any).settings = {};
        script.src = HILLTOPADS_CONFIG.inpage_push.scriptSrc;
        script.async = true;
        script.referrerPolicy = 'no-referrer-when-downgrade';
        document.head.appendChild(script);
      }
    } else {
      // Load Monetag MultiTag script as default fallback
      if (!document.getElementById('monetag-multitag')) {
        const script = document.createElement('script');
        script.id = 'monetag-multitag';
        script.src = MONETAG_MULTITAG_SRC;
        script.dataset.zone = MONETAG_MULTITAG_ZONE;
        script.dataset.cfasync = 'false';
        script.async = true;
        document.head.appendChild(script);
      }
    }
  }, []);

  return null;
}

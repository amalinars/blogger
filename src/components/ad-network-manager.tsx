'use client';

import { useEffect, useRef } from 'react';
import {
  getAdProvider,
  ADSTERRA_POPUNDER_SRC,
  ADSTERRA_SOCIALBAR_SRC,
  MONETAG_MULTITAG_SRC,
  MONETAG_MULTITAG_ZONE,
  EXOCLICK_POPUNDER_CODE,
  EXOCLICK_INPAGE_PUSH_ZONE_ID,
  EXOCLICK_STICKY_ZONE_ID,
  EXOCLICK_NATIVE_SCRIPT,
} from '@/lib/ads';

export function AdNetworkManager() {
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

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

      // Load ExoClick AdProvider Script once & serve widgets
      if (!document.getElementById('exoclick-native-script')) {
        const script = document.createElement('script');
        script.id = 'exoclick-native-script';
        script.async = true;
        script.type = 'application/javascript';
        script.src = EXOCLICK_NATIVE_SCRIPT;
        script.onload = () => {
          try {
            (window.AdProvider = window.AdProvider || []).push({ serve: {} });
          } catch {}
        };
        document.body.appendChild(script);
      } else {
        try {
          (window.AdProvider = window.AdProvider || []).push({ serve: {} });
        } catch {}
      }
    } else if (provider === 'monetag') {
      // Load Monetag MultiTag script
      if (!document.getElementById('monetag-multitag')) {
        const script = document.createElement('script');
        script.id = 'monetag-multitag';
        script.src = MONETAG_MULTITAG_SRC;
        script.dataset.zone = MONETAG_MULTITAG_ZONE;
        script.dataset.cfasync = 'false';
        script.async = true;
        document.head.appendChild(script);
      }
    } else {
      // Load Adsterra Popunder
      if (!document.getElementById('adsterra-popunder')) {
        const popScript = document.createElement('script');
        popScript.id = 'adsterra-popunder';
        popScript.src = ADSTERRA_POPUNDER_SRC;
        popScript.dataset.cfasync = 'false';
        popScript.async = true;
        document.body.appendChild(popScript);
      }

      // Load Adsterra Social Bar
      if (!document.getElementById('adsterra-socialbar')) {
        const barScript = document.createElement('script');
        barScript.id = 'adsterra-socialbar';
        barScript.src = ADSTERRA_SOCIALBAR_SRC;
        barScript.dataset.cfasync = 'false';
        barScript.async = true;
        document.body.appendChild(barScript);
      }
    }
  }, []);

  return null;
}

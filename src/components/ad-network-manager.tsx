'use client';

import { useEffect, useRef } from 'react';
import {
  getAdProvider,
  ADSTERRA_POPUNDER_SRC,
  ADSTERRA_SOCIALBAR_SRC,
  MONETAG_MULTITAG_SRC,
  MONETAG_MULTITAG_ZONE,
} from '@/lib/ads';

export function AdNetworkManager() {
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const provider = getAdProvider();

    if (provider === 'monetag') {
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

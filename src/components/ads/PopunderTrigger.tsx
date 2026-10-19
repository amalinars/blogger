'use client';

import { useEffect } from 'react';

/**
 * Invisible First-Click Trigger to guarantee Popunder activation.
 * Adsterra popunders require an explicit user interaction event.
 * This listener catches the first touch/click anywhere on the viewport.
 */
export function PopunderTrigger() {
  useEffect(() => {
    let triggered = false;

    const handleFirstInteraction = () => {
      if (triggered) return;
      triggered = true;

      // Small dummy event dispatch to ensure popunder script triggers
      window.dispatchEvent(new Event('adsterra_pop_ready'));

      // Remove listeners once first interaction has taken place
      window.removeEventListener('click', handleFirstInteraction);
      window.removeEventListener('touchstart', handleFirstInteraction);
    };

    window.addEventListener('click', handleFirstInteraction, { passive: true, once: true });
    window.addEventListener('touchstart', handleFirstInteraction, { passive: true, once: true });

    return () => {
      window.removeEventListener('click', handleFirstInteraction);
      window.removeEventListener('touchstart', handleFirstInteraction);
    };
  }, []);

  return null;
}

'use client';

import { useEffect } from 'react';

const VIEWPORT_LOCK_CLASS = 'kiosk-viewport-lock';
const KIOSK_VIEWPORT_HEIGHT_VAR = '--kiosk-viewport-height';
const KIOSK_VIEWPORT_WIDTH_VAR = '--kiosk-viewport-width';
const SETTLE_DELAYS_MS = [80, 180, 360, 720] as const;

function getVisualViewportSize() {
  const viewport = window.visualViewport;
  return {
    height: Math.round(viewport?.height || window.innerHeight),
    width: Math.round(viewport?.width || window.innerWidth),
  };
}

export function useKioskViewportLock() {
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    let frameId = 0;
    let settleTimers: number[] = [];

    const clearSettledTimers = () => {
      for (const timer of settleTimers) {
        window.clearTimeout(timer);
      }
      settleTimers = [];
    };

    const syncViewport = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => {
        const { height, width } = getVisualViewportSize();
        html.style.setProperty(KIOSK_VIEWPORT_HEIGHT_VAR, `${height}px`);
        html.style.setProperty(KIOSK_VIEWPORT_WIDTH_VAR, `${width}px`);
        window.scrollTo(0, 0);
      });
    };

    const syncAfterViewportSettles = () => {
      clearSettledTimers();
      syncViewport();
      settleTimers = SETTLE_DELAYS_MS.map((delay) => window.setTimeout(syncViewport, delay));
    };

    html.classList.add(VIEWPORT_LOCK_CLASS);
    body.classList.add(VIEWPORT_LOCK_CLASS);
    syncAfterViewportSettles();

    window.addEventListener('resize', syncAfterViewportSettles, { passive: true });
    window.addEventListener('orientationchange', syncAfterViewportSettles, { passive: true });
    window.visualViewport?.addEventListener('resize', syncAfterViewportSettles, {
      passive: true,
    });
    window.visualViewport?.addEventListener('scroll', syncAfterViewportSettles, {
      passive: true,
    });

    return () => {
      clearSettledTimers();
      window.cancelAnimationFrame(frameId);
      window.removeEventListener('resize', syncAfterViewportSettles);
      window.removeEventListener('orientationchange', syncAfterViewportSettles);
      window.visualViewport?.removeEventListener('resize', syncAfterViewportSettles);
      window.visualViewport?.removeEventListener('scroll', syncAfterViewportSettles);
      html.classList.remove(VIEWPORT_LOCK_CLASS);
      body.classList.remove(VIEWPORT_LOCK_CLASS);
      html.style.removeProperty(KIOSK_VIEWPORT_HEIGHT_VAR);
      html.style.removeProperty(KIOSK_VIEWPORT_WIDTH_VAR);
    };
  }, []);
}

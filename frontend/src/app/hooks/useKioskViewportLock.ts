'use client';

import { useEffect } from 'react';

const VIEWPORT_LOCK_CLASS = 'kiosk-viewport-lock';
const KIOSK_VIEWPORT_HEIGHT_VAR = '--kiosk-viewport-height';
const KIOSK_VIEWPORT_WIDTH_VAR = '--kiosk-viewport-width';
const SETTLE_DELAYS_MS = [80, 180, 360, 720] as const;
const VISUAL_VIEWPORT_SCALE_EPSILON = 0.01;
const VISUAL_VIEWPORT_OFFSET_EPSILON = 1;

type KioskViewportWindow = Pick<Window, 'innerHeight' | 'innerWidth'> & {
  visualViewport?: Pick<VisualViewport, 'height' | 'offsetLeft' | 'offsetTop' | 'scale' | 'width'> | null;
};

type KioskGestureTarget = Pick<EventTarget, 'addEventListener' | 'removeEventListener'>;

function getLayoutViewportSize(target: KioskViewportWindow) {
  return {
    height: Math.round(target.innerHeight),
    width: Math.round(target.innerWidth),
  };
}

function isVisualViewportAtLayoutScale(
  viewport: KioskViewportWindow['visualViewport'],
) {
  if (!viewport) {
    return false;
  }

  const scale = viewport.scale ?? 1;
  const offsetLeft = viewport.offsetLeft ?? 0;
  const offsetTop = viewport.offsetTop ?? 0;

  return (
    Math.abs(scale - 1) <= VISUAL_VIEWPORT_SCALE_EPSILON &&
    Math.abs(offsetLeft) < VISUAL_VIEWPORT_OFFSET_EPSILON &&
    Math.abs(offsetTop) < VISUAL_VIEWPORT_OFFSET_EPSILON
  );
}

export function getKioskViewportSize(target: KioskViewportWindow = window) {
  const layoutSize = getLayoutViewportSize(target);
  const viewport = target.visualViewport;

  if (!isVisualViewportAtLayoutScale(viewport)) {
    return layoutSize;
  }

  return {
    height: Math.max(layoutSize.height, Math.round(viewport?.height || layoutSize.height)),
    width: Math.max(layoutSize.width, Math.round(viewport?.width || layoutSize.width)),
  };
}

export function addKioskGestureSuppression(
  documentTarget: KioskGestureTarget = document,
  windowTarget: KioskGestureTarget = window,
) {
  const nonPassiveOptions: AddEventListenerOptions = { passive: false };

  const preventDefault = (event: Event) => {
    event.preventDefault();
  };

  const preventMultiTouchMove = (event: TouchEvent) => {
    if (event.touches.length > 1) {
      event.preventDefault();
    }
  };

  const registrations: Array<{
    target: KioskGestureTarget;
    type: string;
    listener: EventListener;
  }> = [
    { target: documentTarget, type: 'gesturestart', listener: preventDefault },
    { target: documentTarget, type: 'gesturechange', listener: preventDefault },
    { target: documentTarget, type: 'gestureend', listener: preventDefault },
    { target: documentTarget, type: 'touchmove', listener: preventMultiTouchMove as EventListener },
    { target: windowTarget, type: 'gesturestart', listener: preventDefault },
    { target: windowTarget, type: 'gesturechange', listener: preventDefault },
    { target: windowTarget, type: 'gestureend', listener: preventDefault },
  ];

  for (const { listener, target, type } of registrations) {
    target.addEventListener(type, listener, nonPassiveOptions);
  }

  return () => {
    for (const { listener, target, type } of registrations) {
      target.removeEventListener(type, listener);
    }
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
        const { height, width } = getKioskViewportSize();
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
    const removeKioskGestureSuppression = addKioskGestureSuppression();

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
      removeKioskGestureSuppression();
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

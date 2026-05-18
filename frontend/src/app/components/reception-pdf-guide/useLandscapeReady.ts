import { useEffect, useState } from 'react';

export function useLandscapeReady(): boolean {
  const [landscape, setLandscape] = useState(false);

  useEffect(() => {
    let frameId = 0;
    let settleTimers: number[] = [];

    const getLandscape = () => {
      const mq = window.matchMedia('(orientation: landscape)');
      const viewport = window.visualViewport;
      const width = viewport?.width || window.innerWidth;
      const height = viewport?.height || window.innerHeight;
      return mq.matches || width > height;
    };

    const clearSettledTimers = () => {
      for (const timer of settleTimers) {
        window.clearTimeout(timer);
      }
      settleTimers = [];
    };

    const update = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => {
        setLandscape(getLandscape());
      });
    };

    const updateAfterViewportSettles = () => {
      clearSettledTimers();
      update();
      settleTimers = [80, 180, 360].map((delay) => window.setTimeout(update, delay));
    };

    updateAfterViewportSettles();
    const mq = window.matchMedia('(orientation: landscape)');
    mq.addEventListener('change', updateAfterViewportSettles);
    window.addEventListener('resize', updateAfterViewportSettles);
    window.addEventListener('orientationchange', updateAfterViewportSettles);
    window.visualViewport?.addEventListener('resize', updateAfterViewportSettles);

    return () => {
      clearSettledTimers();
      window.cancelAnimationFrame(frameId);
      mq.removeEventListener('change', updateAfterViewportSettles);
      window.removeEventListener('resize', updateAfterViewportSettles);
      window.removeEventListener('orientationchange', updateAfterViewportSettles);
      window.visualViewport?.removeEventListener('resize', updateAfterViewportSettles);
    };
  }, []);

  return landscape;
}

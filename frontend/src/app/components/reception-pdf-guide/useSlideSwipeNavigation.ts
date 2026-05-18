import { useCallback, useRef } from 'react';
import type React from 'react';

const SWIPE_MIN_DISTANCE_PX = 64;
const SWIPE_HORIZONTAL_DOMINANCE = 1.35;

export function useSlideSwipeNavigation(nextSlide: () => void, previousSlide: () => void) {
  const swipeStartRef = useRef<{
    pointerId: number | null;
    x: number;
    y: number;
  } | null>(null);

  const handleSwipeDelta = useCallback(
    (deltaX: number, deltaY: number) => {
      const absX = Math.abs(deltaX);
      const absY = Math.abs(deltaY);
      if (
        absX < SWIPE_MIN_DISTANCE_PX ||
        absX < absY * SWIPE_HORIZONTAL_DOMINANCE
      ) {
        return;
      }
      if (deltaX < 0) {
        nextSlide();
      } else {
        previousSlide();
      }
    },
    [nextSlide, previousSlide],
  );

  const onSlidePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!event.isPrimary || event.button !== 0) {
      return;
    }
    swipeStartRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onSlidePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = swipeStartRef.current;
    if (!start || start.pointerId !== event.pointerId) {
      return;
    }
    swipeStartRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    handleSwipeDelta(event.clientX - start.x, event.clientY - start.y);
  };

  const onSlidePointerCancel = (event: React.PointerEvent<HTMLDivElement>) => {
    if (swipeStartRef.current?.pointerId === event.pointerId) {
      swipeStartRef.current = null;
    }
  };

  return {
    onSlidePointerCancel,
    onSlidePointerDown,
    onSlidePointerUp,
  };
}

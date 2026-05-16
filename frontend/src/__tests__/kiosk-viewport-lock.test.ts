import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  addKioskGestureSuppression,
  getKioskViewportSize,
} from '../app/hooks/useKioskViewportLock';

type RegisteredListener = {
  listener: EventListenerOrEventListenerObject;
  options?: boolean | AddEventListenerOptions;
  type: string;
};

class FakeEventTarget {
  public readonly added: RegisteredListener[] = [];
  public readonly removed: RegisteredListener[] = [];

  addEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
    options?: boolean | AddEventListenerOptions,
  ) {
    this.added.push({ listener, options, type });
  }

  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ) {
    this.removed.push({ listener, type });
  }
}

test('kiosk viewport size keeps the layout viewport while visualViewport is pinched', () => {
  const size = getKioskViewportSize({
    innerHeight: 768,
    innerWidth: 1024,
    visualViewport: {
      height: 512,
      offsetLeft: 0,
      offsetTop: 0,
      scale: 1.5,
      width: 683,
    },
  });

  assert.deepEqual(size, {
    height: 768,
    width: 1024,
  });
});

test('kiosk viewport size ignores visualViewport offsets caused by pan after zoom', () => {
  const size = getKioskViewportSize({
    innerHeight: 768,
    innerWidth: 1024,
    visualViewport: {
      height: 700,
      offsetLeft: 120,
      offsetTop: 32,
      scale: 1,
      width: 900,
    },
  });

  assert.deepEqual(size, {
    height: 768,
    width: 1024,
  });
});

test('kiosk viewport size does not shrink below the layout viewport during Safari visualViewport jitter', () => {
  const size = getKioskViewportSize({
    innerHeight: 768,
    innerWidth: 1024,
    visualViewport: {
      height: 744,
      offsetLeft: 0,
      offsetTop: 0,
      scale: 1,
      width: 1000,
    },
  });

  assert.deepEqual(size, {
    height: 768,
    width: 1024,
  });
});

test('kiosk gesture suppression registers non-passive gesture and multi-touch move listeners', () => {
  const documentTarget = new FakeEventTarget();
  const windowTarget = new FakeEventTarget();

  const cleanup = addKioskGestureSuppression(documentTarget, windowTarget);

  assert.deepEqual(
    documentTarget.added.map(({ type }) => type),
    ['gesturestart', 'gesturechange', 'gestureend', 'touchmove'],
  );
  assert.deepEqual(
    windowTarget.added.map(({ type }) => type),
    ['gesturestart', 'gesturechange', 'gestureend'],
  );
  assert.equal(
    documentTarget.added.every(({ options }) => {
      return typeof options === 'object' && options.passive === false;
    }),
    true,
  );
  assert.equal(
    windowTarget.added.every(({ options }) => {
      return typeof options === 'object' && options.passive === false;
    }),
    true,
  );

  const gestureStart = documentTarget.added.find(({ type }) => type === 'gesturestart');
  let gesturePrevented = false;
  (gestureStart?.listener as EventListener)({
    preventDefault: () => {
      gesturePrevented = true;
    },
  } as Event);
  assert.equal(gesturePrevented, true);

  const touchMove = documentTarget.added.find(({ type }) => type === 'touchmove');
  let singleTouchPrevented = false;
  (touchMove?.listener as EventListener)({
    preventDefault: () => {
      singleTouchPrevented = true;
    },
    touches: [{}],
  } as unknown as TouchEvent);
  assert.equal(singleTouchPrevented, false);

  let multiTouchPrevented = false;
  (touchMove?.listener as EventListener)({
    preventDefault: () => {
      multiTouchPrevented = true;
    },
    touches: [{}, {}],
  } as unknown as TouchEvent);
  assert.equal(multiTouchPrevented, true);

  cleanup();

  assert.deepEqual(
    documentTarget.removed.map(({ type }) => type),
    ['gesturestart', 'gesturechange', 'gestureend', 'touchmove'],
  );
  assert.deepEqual(
    windowTarget.removed.map(({ type }) => type),
    ['gesturestart', 'gesturechange', 'gestureend'],
  );
});

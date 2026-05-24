import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

type DeviceWindow = EventTarget & {
  __engineerCafe?: Record<string, unknown>;
  setInterval: typeof global.setInterval;
};

const originalWindow = global.window;
const originalFetch = global.fetch;
const originalDateNow = Date.now;

function createWindow(): DeviceWindow {
  return Object.assign(new EventTarget(), {
    setInterval: global.setInterval,
  }) as DeviceWindow;
}

afterEach(async () => {
  global.fetch = originalFetch;
  Object.defineProperty(Date, 'now', {
    configurable: true,
    value: originalDateNow,
  });
  (global as typeof globalThis & { window?: Window & typeof globalThis }).window = originalWindow;

  const deviceWebhook = await import('../lib/api/device-webhook');
  deviceWebhook.stopSensorPolling();
});

test('handleDeviceDetection dispatches the browser device-detection event', async () => {
  const windowMock = createWindow();
  (global as unknown as { window: Window & typeof globalThis }).window =
    windowMock as unknown as Window & typeof globalThis;

  const events: Array<Record<string, unknown>> = [];
  windowMock.addEventListener('device-detection', (event) => {
    events.push((event as CustomEvent<Record<string, unknown>>).detail);
  });

  const { handleDeviceDetection } = await import('../lib/api/device-webhook');
  handleDeviceDetection({
    type: 'sensor_triggered',
    device_id: 'm5stack-001',
    timestamp: '2026-04-04T10:00:00.000Z',
  });

  assert.equal(events.length, 1);
  assert.equal(events[0].device_id, 'm5stack-001');
});

test('startSensorPolling dispatches device-detection when backend reports a new trigger', async () => {
  const windowMock = createWindow();
  (global as unknown as { window: Window & typeof globalThis }).window =
    windowMock as unknown as Window & typeof globalThis;

  const events: Array<Record<string, unknown>> = [];
  windowMock.addEventListener('device-detection', (event) => {
    events.push((event as CustomEvent<Record<string, unknown>>).detail);
  });

  global.fetch = (async () =>
    new Response(
      JSON.stringify({
        triggered: true,
        device_id: 'm5stack-poll-test',
        sensor_type: 'pir_sr04',
        distance_mm: 65,
        timestamp: 1712221538.085,
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }
    )) as typeof fetch;

  const { startSensorPolling } = await import('../lib/api/device-webhook');
  startSensorPolling('m5stack-poll-test', 60_000);

  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(events.length, 1);
  assert.equal(events[0].device_id, 'm5stack-poll-test');
  assert.equal(events[0].type, 'sensor_triggered');
  assert.deepEqual(events[0].data, {
    sensor_type: 'pir_sr04',
    distance_mm: 65,
  });
});

test('startSensorPolling applies an initial lookback window', async () => {
  const windowMock = createWindow();
  (global as unknown as { window: Window & typeof globalThis }).window =
    windowMock as unknown as Window & typeof globalThis;

  let capturedUrl = '';
  Object.defineProperty(Date, 'now', {
    configurable: true,
    value: () => 1_712_221_540_000,
  });
  global.fetch = (async (input) => {
    capturedUrl = String(input);
    return new Response(JSON.stringify({ triggered: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  const { startSensorPolling } = await import('../lib/api/device-webhook');
  startSensorPolling('m5stack-lookback-test', 60_000);

  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const url = new URL(capturedUrl, 'https://frontend.test');
  assert.equal(url.searchParams.get('device_id'), 'm5stack-lookback-test');
  assert.equal(url.searchParams.get('since'), '1712221480');
});

test('stopSensorPolling suppresses a stale in-flight sensor response', async () => {
  const windowMock = createWindow();
  (global as unknown as { window: Window & typeof globalThis }).window =
    windowMock as unknown as Window & typeof globalThis;

  const events: Array<Record<string, unknown>> = [];
  windowMock.addEventListener('device-detection', (event) => {
    events.push((event as CustomEvent<Record<string, unknown>>).detail);
  });

  let resolveFetch: ((value: Response) => void) | null = null;
  global.fetch =
    ((async () =>
      await new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      })) as unknown as typeof fetch);

  const { startSensorPolling, stopSensorPolling } = await import('../lib/api/device-webhook');
  startSensorPolling('m5stack-stop-test', 60_000);
  stopSensorPolling();

  const stopTestResolver = resolveFetch as ((value: Response) => void) | null;
  if (stopTestResolver) {
    stopTestResolver(
      new Response(
        JSON.stringify({
          triggered: true,
          device_id: 'm5stack-stop-test',
          sensor_type: 'pir_sr04',
          distance_mm: 70,
          timestamp: 1712221539.085,
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    );
  }

  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(events.length, 0);
});

test('restartSensorPolling immediately polls new session even if old request is in flight', async () => {
  const windowMock = createWindow();
  (global as unknown as { window: Window & typeof globalThis }).window =
    windowMock as unknown as Window & typeof globalThis;

  const events: Array<Record<string, unknown>> = [];
  windowMock.addEventListener('device-detection', (event) => {
    events.push((event as CustomEvent<Record<string, unknown>>).detail);
  });

  let resolveFirstFetch: ((value: Response) => void) | null = null;
  let fetchCount = 0;
  global.fetch = (async () => {
    fetchCount += 1;
    if (fetchCount === 1) {
      return await new Promise<Response>((resolve) => {
        resolveFirstFetch = resolve;
      });
    }

    return new Response(
      JSON.stringify({
        triggered: true,
        device_id: 'm5stack-restart-test',
        sensor_type: 'pir_sr04',
        distance_mm: 80,
        timestamp: 1712221540.085,
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }) as typeof fetch;

  const { startSensorPolling, stopSensorPolling } = await import('../lib/api/device-webhook');
  startSensorPolling('m5stack-restart-test', 60_000);
  stopSensorPolling();
  startSensorPolling('m5stack-restart-test', 60_000);

  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(fetchCount, 2);
  assert.equal(events.length, 1);

  const restartTestResolver = resolveFirstFetch as ((value: Response) => void) | null;
  if (restartTestResolver) {
    restartTestResolver(
      new Response(
        JSON.stringify({
          triggered: true,
          device_id: 'm5stack-restart-test',
          sensor_type: 'pir_sr04',
          distance_mm: 90,
          timestamp: 1712221541.085,
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    );
  }

  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(events.length, 1);
});

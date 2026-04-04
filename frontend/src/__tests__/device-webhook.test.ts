import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

type DeviceWindow = EventTarget & {
  __engineerCafe?: Record<string, unknown>;
  setInterval: typeof global.setInterval;
};

const originalWindow = global.window;
const originalFetch = global.fetch;

function createWindow(): DeviceWindow {
  return Object.assign(new EventTarget(), {
    setInterval: global.setInterval,
  }) as DeviceWindow;
}

afterEach(async () => {
  global.fetch = originalFetch;
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

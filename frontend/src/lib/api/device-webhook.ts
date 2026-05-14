import { getSensorStatus } from '@/lib/reception-api';

export interface DeviceDetectionEvent {
  type: 'sensor_triggered' | 'nfc_detected' | 'button_pressed';
  device_id?: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

export const DEFAULT_KIOSK_DEVICE_ID = 'm5stack-001';
export const KIOSK_DEVICE_ID_STORAGE_KEY = 'engineer_cafe_kiosk_device_id';
const DEFAULT_SENSOR_POLL_INTERVAL_MS = 1000;

let sensorPollingIntervalId: number | null = null;
let lastSeenSensorTimestampByDevice = new Map<string, number>();
let activePollingSessionToken = 0;
let pollingInFlightSessionToken: number | null = null;

/**
 * Future: server webhooks or edge hardware can call the same entry points as the kiosk
 * screen buttons by dispatching `device-detection` or by exposing a thin adapter that
 * invokes the same `setKioskPhase` / transition logic as `frontend/src/app/page.tsx`.
 * Not wired in the current release (screen-first).
 */

/** Dispatch a custom event; kiosk home (`page.tsx`) plays the welcome greeting when phase is idle. */
export function handleDeviceDetection(event: DeviceDetectionEvent): void {
  window.dispatchEvent(new CustomEvent('device-detection', { detail: event }));
}

async function pollSensorStatus(deviceId: string, sessionToken: number): Promise<void> {
  if (sessionToken !== activePollingSessionToken) {
    return;
  }

  if (pollingInFlightSessionToken === sessionToken) {
    return;
  }

  pollingInFlightSessionToken = sessionToken;

  try {
    const data = await getSensorStatus(
      deviceId,
      lastSeenSensorTimestampByDevice.get(deviceId) ?? 0
    );

    if (sessionToken !== activePollingSessionToken) {
      return;
    }

    if (!data.triggered || typeof data.timestamp !== 'number') {
      return;
    }

    lastSeenSensorTimestampByDevice.set(deviceId, data.timestamp);
    handleDeviceDetection({
      type: 'sensor_triggered',
      device_id: data.device_id ?? deviceId,
      timestamp: new Date(data.timestamp * 1000).toISOString(),
      data: {
        sensor_type: data.sensor_type,
        distance_mm: data.distance_mm,
      },
    });
  } catch {
    // Best-effort polling; transient network errors should not break kiosk idle mode.
  } finally {
    if (pollingInFlightSessionToken === sessionToken) {
      pollingInFlightSessionToken = null;
    }
  }
}

function readConfiguredKioskDeviceId(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const stored = window.localStorage.getItem(KIOSK_DEVICE_ID_STORAGE_KEY)?.trim();
    return stored ? stored : null;
  } catch {
    return null;
  }
}

export function resolveKioskDeviceId(deviceId?: string): string {
  const explicitDeviceId = deviceId?.trim();
  if (explicitDeviceId) {
    return explicitDeviceId;
  }

  const storedDeviceId = readConfiguredKioskDeviceId();
  if (storedDeviceId) {
    return storedDeviceId;
  }

  const envDeviceId = process.env.NEXT_PUBLIC_KIOSK_DEVICE_ID?.trim();
  return envDeviceId || DEFAULT_KIOSK_DEVICE_ID;
}

export function startSensorPolling(
  deviceId?: string,
  intervalMs = DEFAULT_SENSOR_POLL_INTERVAL_MS
): void {
  if (typeof window === 'undefined') {
    return;
  }

  const resolvedDeviceId = resolveKioskDeviceId(deviceId);

  stopSensorPolling();
  activePollingSessionToken += 1;
  const sessionToken = activePollingSessionToken;
  // Initialize since to now so pre-existing (stale) events are ignored
  if (!lastSeenSensorTimestampByDevice.has(resolvedDeviceId)) {
    lastSeenSensorTimestampByDevice.set(resolvedDeviceId, Date.now() / 1000);
  }
  void pollSensorStatus(resolvedDeviceId, sessionToken);
  sensorPollingIntervalId = window.setInterval(() => {
    void pollSensorStatus(resolvedDeviceId, sessionToken);
  }, intervalMs);
}

export function stopSensorPolling(): void {
  activePollingSessionToken += 1;
  if (sensorPollingIntervalId !== null) {
    clearInterval(sensorPollingIntervalId);
    sensorPollingIntervalId = null;
  }
}

// Expose globally for external device integration (M5Stack, NFC readers, etc.)
if (typeof window !== 'undefined') {
  const win = window as unknown as Record<string, unknown>;
  const existing =
    typeof win.__engineerCafe === 'object' ? win.__engineerCafe : {};

  win.__engineerCafe = {
    ...(existing as Record<string, unknown>),
    triggerDetection: handleDeviceDetection,
  };
}

import { getSensorStatus } from '@/lib/reception-api';

export interface DeviceDetectionEvent {
  type: 'sensor_triggered' | 'nfc_detected' | 'button_pressed';
  device_id?: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

const DEFAULT_DEVICE_ID = 'm5stack-001';
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

export function startSensorPolling(
  deviceId = DEFAULT_DEVICE_ID,
  intervalMs = DEFAULT_SENSOR_POLL_INTERVAL_MS
): void {
  if (typeof window === 'undefined') {
    return;
  }

  stopSensorPolling();
  activePollingSessionToken += 1;
  const sessionToken = activePollingSessionToken;
  void pollSensorStatus(deviceId, sessionToken);
  sensorPollingIntervalId = window.setInterval(() => {
    void pollSensorStatus(deviceId, sessionToken);
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

export interface DeviceDetectionEvent {
  type: 'sensor_triggered' | 'nfc_detected' | 'button_pressed';
  device_id?: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

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

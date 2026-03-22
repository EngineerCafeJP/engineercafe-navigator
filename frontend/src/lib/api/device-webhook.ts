export interface DeviceDetectionEvent {
  type: 'sensor_triggered' | 'nfc_detected' | 'button_pressed';
  device_id?: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

/** Dispatch a custom event that ReceptionPanel listens to. */
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

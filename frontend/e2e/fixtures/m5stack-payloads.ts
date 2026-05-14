/**
 * Shared POST bodies for /api/reception/sensor-trigger contract tests.
 * Schema matches backend SensorTriggerRequest and M5Stack firmware payloads.
 */
const DEFAULT_FIRMWARE_DEVICE_ID = 'm5stack-001';
const FIRMWARE_SENSOR_TYPE = 'pir_tof';

function firmwarePayload(deviceId = DEFAULT_FIRMWARE_DEVICE_ID, distanceMm = 280) {
  return {
    sensor_type: FIRMWARE_SENSOR_TYPE,
    distance_mm: distanceMm,
    device_id: deviceId,
  };
}

export const m5stackPayloads = {
  /** Matches firmware SENSOR_TYPE and frontend default kiosk device_id. */
  firmwareClose: firmwarePayload,
  tofClose: firmwarePayload(),
  tofFar: firmwarePayload(DEFAULT_FIRMWARE_DEVICE_ID, 800),
  invalidLongSensorType: {
    sensor_type: 'X'.repeat(51),
    distance_mm: 280,
    device_id: 'm5stack-validation',
  },
  rateLimitDevice: (suffix: string = String(Date.now())) => ({
    sensor_type: FIRMWARE_SENSOR_TYPE,
    distance_mm: 280,
    device_id: `m5stack-e2e-rate-limit-${suffix}`,
  }),
};

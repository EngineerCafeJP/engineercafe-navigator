/**
 * Shared POST bodies for /api/reception/sensor-trigger contract tests.
 * Schema matches backend SensorTriggerRequest (required distance_mm + device_id).
 */
export const m5stackPayloads = {
  /** Matches frontend DEFAULT_DEVICE_ID in device-webhook polling. */
  tofClose: { sensor_type: 'ToF', distance_mm: 350, device_id: 'm5stack-001' },
  tofFar: { sensor_type: 'ToF', distance_mm: 800, device_id: 'm5stack-001' },
  invalidLongSensorType: {
    sensor_type: 'X'.repeat(51),
    distance_mm: 350,
    device_id: 'm5stack-validation',
  },
  rateLimitDevice: {
    sensor_type: 'ToF',
    distance_mm: 500,
    device_id: 'm5stack-e2e-rate-limit',
  },
};

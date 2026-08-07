export type KioskPhase = 'notice' | 'idle' | 'voice' | 'ocr' | 'slides';

/**
 * Kiosk / signage idle timeout (ms). After assistant speech ends (or equivalent),
 * return to kiosk idle if the user does not interact within this window.
 */
export const KIOSK_IDLE_MS: number = (() => {
  const raw = process.env.NEXT_PUBLIC_KIOSK_IDLE_MS;
  if (raw === undefined || raw === '') {
    return 60_000;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 60_000;
})();

/**
 * After Welcome runs (button or device-detection), ignore further Welcome triggers for this long (ms).
 * Override with `NEXT_PUBLIC_KIOSK_WELCOME_COOLDOWN_MS`.
 */
export const KIOSK_WELCOME_COOLDOWN_MS: number = (() => {
  const raw = process.env.NEXT_PUBLIC_KIOSK_WELCOME_COOLDOWN_MS;
  if (raw === undefined || raw === '') {
    return 12_000;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 12_000;
})();

/**
 * Device/sensor-triggered Welcome cooldown (ms). This is longer than the
 * virtual button guard because physical sensors can fire repeatedly while a
 * visitor remains near the kiosk.
 */
export const KIOSK_DEVICE_WELCOME_COOLDOWN_MS: number = (() => {
  const raw = process.env.NEXT_PUBLIC_KIOSK_DEVICE_WELCOME_COOLDOWN_MS;
  if (raw === undefined || raw === '') {
    return 60_000;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 60_000;
})();

export const KIOSK_TRIGGER_MODE_STORAGE_KEY = 'engineer_cafe_kiosk_trigger_mode';

export type KioskTriggerMode = 'screen' | 'device';

export function readKioskTriggerMode(): KioskTriggerMode {
  if (typeof window === 'undefined') {
    return 'screen';
  }
  try {
    const v = window.localStorage.getItem(KIOSK_TRIGGER_MODE_STORAGE_KEY);
    return v === 'device' ? 'device' : 'screen';
  } catch {
    return 'screen';
  }
}

export function writeKioskTriggerMode(mode: KioskTriggerMode): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(KIOSK_TRIGGER_MODE_STORAGE_KEY, mode);
  } catch {
    // ignore quota / private mode
  }
}

export const KIOSK_MIC_MODE_STORAGE_KEY = 'engineer_cafe_kiosk_mic_mode';

/** Toggle: tap to start/stop listening. Push-to-talk: hold to listen. */
export type KioskMicMode = 'toggle' | 'push_to_talk';
export function readKioskMicMode(): KioskMicMode {
  if (typeof window === 'undefined') {
    return 'toggle';
  }
  try {
    const v = window.localStorage.getItem(KIOSK_MIC_MODE_STORAGE_KEY);
    return v === 'push_to_talk' ? 'push_to_talk' : 'toggle';
  } catch {
    return 'toggle';
  }
}

export function writeKioskMicMode(mode: KioskMicMode): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(KIOSK_MIC_MODE_STORAGE_KEY, mode);
  } catch {
    // ignore
  }
}

/**
 * TTS 合成速度（倍率）。1.0=標準・小さいほど遅い。
 * UI (SpeakerSettings) のスライダーで調整し、/api/voice text_to_speech に
 * speed として渡される。未設定時はサーバー側設定 (PIPER_SPEED / KOKORO_TTS_SPEED) に従う。
 */
export const KIISK_TTS_SPEED_STORAGE_KEY = 'engineer_cafe_kiosk_tts_speed';

export const KIISK_TTS_SPEED_MIN = 0.5;
export const KIISK_TTS_SPEED_MAX = 1.5;
export const KIISK_TTS_SPEED_STEP = 0.05;
export const KIISK_TTS_SPEED_DEFAULT = 0.85;

export function readKioskTtsSpeed(): number {
  if (typeof window === 'undefined') {
    return KIISK_TTS_SPEED_DEFAULT;
  }
  try {
    const v = Number(window.localStorage.getItem(KIISK_TTS_SPEED_STORAGE_KEY));
    if (Number.isFinite(v) && v >= KIISK_TTS_SPEED_MIN && v <= KIISK_TTS_SPEED_MAX) {
      return v;
    }
  } catch {
    // ignore
  }
  return KIISK_TTS_SPEED_DEFAULT;
}

export function writeKioskTtsSpeed(speed: number): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(KIISK_TTS_SPEED_STORAGE_KEY, String(speed));
  } catch {
    // ignore
  }
}

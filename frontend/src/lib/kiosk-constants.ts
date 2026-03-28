export type KioskPhase = 'notice' | 'idle' | 'voice' | 'ocr' | 'slides';

/**
 * Kiosk / signage idle timeout (ms). After assistant speech ends (or equivalent),
 * return to kiosk idle if the user does not interact within this window.
 */
export const KIOSK_IDLE_MS: number = (() => {
  const raw = process.env.NEXT_PUBLIC_KIOSK_IDLE_MS;
  if (raw === undefined || raw === '') {
    return 90_000;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 90_000;
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

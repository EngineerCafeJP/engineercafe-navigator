type UserInteractionCallback = () => void | Promise<void>;

const INTERACTION_EVENTS: Array<'click' | 'touchstart' | 'keydown'> = ['click', 'touchstart', 'keydown'];

let hasUserInteracted = false;
let listenersRegistered = false;
const pendingCallbacks = new Set<UserInteractionCallback>();
let pendingInteractionPromise: Promise<void> | null = null;
let resolvePendingInteraction: (() => void) | null = null;

const isBrowser = (): boolean => typeof window !== 'undefined' && typeof document !== 'undefined';

export const isIOSWebKitAudio = (): boolean => {
  if (!isBrowser()) return false;
  const ua = navigator.userAgent;
  const vendor = navigator.vendor || '';

  if (/iPad|iPhone|iPod/.test(ua)) return true;
  if (
    typeof navigator.platform === 'string' &&
    navigator.platform === 'MacIntel' &&
    (navigator.maxTouchPoints || 0) > 1
  ) {
    return true;
  }

  return (
    /Safari/.test(ua) &&
    /Apple/.test(vendor) &&
    !/Chrome|CriOS|Chromium|Edg/.test(ua) &&
    /Mobile/.test(ua)
  );
};

export type SupportedLang = 'ja' | 'en' | 'zh' | 'ko';

export const getTapToEnableAudioMessage = (language: string = 'ja'): string => {
  const messages: Record<SupportedLang, string> = {
    ja: '音声を有効にするには、もう一度画面をタップしてください',
    en: 'Tap once more to enable audio playback',
    zh: '请再次点按屏幕以启用音频',
    ko: '오디오를 활성화하려면 화면을 한 번 더 탭하세요',
  };
  const lang = language as SupportedLang;
  return messages[lang] ?? messages.en;
};

const clearPendingInteraction = (): void => {
  resolvePendingInteraction?.();
  pendingInteractionPromise = null;
  resolvePendingInteraction = null;
};

const removeInteractionListeners = (): void => {
  if (!listenersRegistered || !isBrowser()) {
    return;
  }

  INTERACTION_EVENTS.forEach((eventType) => {
    document.removeEventListener(eventType, handleFirstUserInteraction, true);
  });
  listenersRegistered = false;
};

const flushPendingCallbacks = (): void => {
  const callbacks = Array.from(pendingCallbacks);
  pendingCallbacks.clear();

  callbacks.forEach((callback) => {
    Promise.resolve(callback()).catch((error) => {
      console.error('[AudioInteractionGate] Failed to handle first user interaction:', error);
    });
  });
};

const unlockAudioInteraction = (): void => {
  if (hasUserInteracted) {
    return;
  }

  hasUserInteracted = true;
  removeInteractionListeners();
  clearPendingInteraction();
  flushPendingCallbacks();
};

function handleFirstUserInteraction(): void {
  unlockAudioInteraction();
}

const ensureInteractionListenersRegistered = (): void => {
  if (hasUserInteracted || listenersRegistered || !isBrowser()) {
    return;
  }

  INTERACTION_EVENTS.forEach((eventType) => {
    document.addEventListener(eventType, handleFirstUserInteraction, {
      capture: true,
      passive: true
    });
  });
  listenersRegistered = true;
};

export const registerAudioInteractionCallback = (callback: UserInteractionCallback): void => {
  if (hasUserInteracted) {
    Promise.resolve(callback()).catch((error) => {
      console.error('[AudioInteractionGate] Failed to run audio interaction callback:', error);
    });
    return;
  }

  pendingCallbacks.add(callback);
  ensureInteractionListenersRegistered();
};

export const waitForAudioUserInteraction = (): Promise<void> => {
  if (hasUserInteracted) {
    return Promise.resolve();
  }

  ensureInteractionListenersRegistered();

  if (!pendingInteractionPromise) {
    pendingInteractionPromise = new Promise<void>((resolve) => {
      resolvePendingInteraction = resolve;
    });
  }

  return pendingInteractionPromise;
};

export const markAudioUserInteraction = (): void => {
  unlockAudioInteraction();
};

export const hasAudioUserInteraction = (): boolean => hasUserInteracted;

export const registerAudioContextResumeOnInteraction = (audioContext: AudioContext): void => {
  registerAudioInteractionCallback(async () => {
    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }
  });
};

export const resetAudioUserInteractionGate = (): void => {
  removeInteractionListeners();
  pendingCallbacks.clear();
  pendingInteractionPromise = null;
  resolvePendingInteraction = null;
  hasUserInteracted = false;
};

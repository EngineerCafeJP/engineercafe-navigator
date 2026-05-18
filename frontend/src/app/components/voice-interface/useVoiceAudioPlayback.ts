import { AudioQueue } from '@/lib/audio-queue';
import { AudioDataProcessor } from '@/lib/audio/audio-data-processor';
import { AudioInteractionManager } from '@/lib/audio/audio-interaction-manager';
import {
  getTapToEnableAudioMessage,
  isIOSWebKitAudio,
} from '@/lib/audio/audio-user-interaction-gate';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import { formatError } from '@/lib/error-messages';
import { LipSyncAnalyzer, type LipSyncFrame } from '@/lib/lip-sync-analyzer';
import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import {
  FALLBACK_NOTICE_LIMIT_PER_SESSION,
  FALLBACK_NOTICE_TEXT,
  LOADING_LABELS,
} from './constants';
import type {
  VoiceInterfaceMetadata,
  VoiceLoadingPhase,
  VoiceSessionState,
} from './types';
import {
  isAudioGestureRequiredError,
  stopAudioPlayback,
} from './utils';

interface VoicePlaybackController {
  notifySpeaking: () => void;
}

interface UseVoiceAudioPlaybackArgs {
  currentLanguage: 'ja' | 'en';
  isMuted: boolean;
  volume: number;
  sessionState: VoiceSessionState;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  onAssistantPlaybackStart?: (payload: { metadata: VoiceInterfaceMetadata | null }) => void;
  voiceController: VoicePlaybackController;
  cancelFastFiller: () => void;
  completeAssistantTurn: (forceSkipAutoResume?: boolean) => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setLoadingMessage: Dispatch<SetStateAction<string>>;
  setLoadingPhase: Dispatch<SetStateAction<VoiceLoadingPhase>>;
  setExclusiveUiLock: Dispatch<SetStateAction<boolean>>;
}

export function useVoiceAudioPlayback({
  currentLanguage,
  isMuted,
  volume,
  sessionState,
  onVisemeControl,
  onAssistantPlaybackStart,
  voiceController,
  cancelFastFiller,
  completeAssistantTurn,
  setError,
  setIsLoading,
  setLoadingMessage,
  setLoadingPhase,
  setExclusiveUiLock,
}: UseVoiceAudioPlaybackArgs) {
  const lipSyncAnalyzerRef = useRef<LipSyncAnalyzer | null>(null);
  const lipSyncTimersRef = useRef<number[]>([]);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const mobileAudioServiceRef = useRef<MobileAudioService | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const pendingIOSPlaybackRef = useRef<{
    audioBase64: string;
    metadata: VoiceInterfaceMetadata | null;
  } | null>(null);
  const isReplayingPendingIOSAudioRef = useRef(false);
  const pendingIOSPlaybackReplayTokenRef = useRef(0);
  const fallbackNoticeCountRef = useRef(0);

  useEffect(() => {
    const q = new AudioQueue();
    audioQueueRef.current = q;
    q.setVolume(isMuted ? 0 : volume);
    return () => {
      q.clear();
      audioQueueRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount bootstrap only
  }, []);

  const clearLipSyncTimers = useCallback(() => {
    lipSyncTimersRef.current.forEach((id) => cancelAnimationFrame(id));
    lipSyncTimersRef.current = [];
    onVisemeControl?.('Closed', 0);
  }, [onVisemeControl]);

  const revokeAudioUrl = useCallback(() => {
    if (!audioUrlRef.current) {
      return;
    }

    URL.revokeObjectURL(audioUrlRef.current);
    audioUrlRef.current = null;
  }, []);

  const cleanupAudioPlayback = useCallback(() => {
    clearLipSyncTimers();
    revokeAudioUrl();
  }, [clearLipSyncTimers, revokeAudioUrl]);

  const ensureAudioService = useCallback(() => {
    if (!mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current = new MobileAudioService({ volume });
    }

    mobileAudioServiceRef.current.setVolume(volume);
    return mobileAudioServiceRef.current;
  }, [volume]);

  const playAudioFallbackNotice = useCallback(() => {
    const message = FALLBACK_NOTICE_TEXT[currentLanguage];
    setError(message);

    if (isMuted || typeof window === 'undefined') {
      return;
    }
    if (fallbackNoticeCountRef.current >= FALLBACK_NOTICE_LIMIT_PER_SESSION) {
      return;
    }
    fallbackNoticeCountRef.current += 1;

    try {
      const AudioContextCtor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (AudioContextCtor) {
        const ctx = new AudioContextCtor();
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = 880;
        gain.gain.value = 0.08;
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start();
        window.setTimeout(() => {
          oscillator.stop();
          void ctx.close().catch(() => {});
        }, 120);
      }
    } catch {
      // Best-effort fallback cue.
    }
  }, [currentLanguage, isMuted, setError]);

  const deferForIOSAudioUnlock = useCallback((
    pendingPlayback?: {
      audioBase64: string;
      metadata: VoiceInterfaceMetadata | null;
    },
  ): boolean => {
    if (!isIOSWebKitAudio()) {
      return false;
    }

    let state: AudioContextState | null = null;
    let isReady = false;
    try {
      const manager = AudioInteractionManager.getInstance();
      state = manager.getAudioContextState();
      isReady = manager.isAudioContextReady() && state === 'running';
    } catch {
      isReady = false;
    }

    if (isReady) {
      return false;
    }

    if (pendingPlayback) {
      pendingIOSPlaybackRef.current = pendingPlayback;
    }

    const message = getTapToEnableAudioMessage(currentLanguage);
    console.warn('[VoiceInterface] iOS AudioContext is not ready; waiting for a tap-to-enable gesture', {
      state,
    });
    cleanupAudioPlayback();
    setError(message);
    setIsLoading(false);
    setLoadingMessage('');
    setLoadingPhase(null);
    setExclusiveUiLock(false);
    completeAssistantTurn(true);
    return true;
  }, [
    cleanupAudioPlayback,
    completeAssistantTurn,
    currentLanguage,
    setError,
    setExclusiveUiLock,
    setIsLoading,
    setLoadingMessage,
    setLoadingPhase,
  ]);

  const scheduleLipSyncFrames = useCallback(
    (frames: LipSyncFrame[]) => {
      if (!onVisemeControl || frames.length === 0) {
        return;
      }
      clearLipSyncTimers();
      const startTime = performance.now();
      const lastFrameTime = frames[frames.length - 1].time;

      let frameIndex = 0;

      const update = () => {
        const elapsed = (performance.now() - startTime) / 1000;
        while (
          frameIndex < frames.length - 1 &&
          frames[frameIndex + 1].time <= elapsed
        ) {
          frameIndex++;
        }
        if (frameIndex < frames.length && frames[frameIndex].time <= elapsed) {
          onVisemeControl(frames[frameIndex].mouthShape, frames[frameIndex].mouthOpen);
        }
        if (elapsed < lastFrameTime + 0.5) {
          const rafId = requestAnimationFrame(update);
          lipSyncTimersRef.current = [rafId];
        } else {
          onVisemeControl('Closed', 0);
        }
      };

      const rafId = requestAnimationFrame(update);
      lipSyncTimersRef.current = [rafId];
    },
    [clearLipSyncTimers, onVisemeControl],
  );

  const analyzeLipSyncFrames = useCallback(async (audioBlob: Blob): Promise<LipSyncFrame[] | null> => {
    try {
      if (!lipSyncAnalyzerRef.current) {
        lipSyncAnalyzerRef.current = new LipSyncAnalyzer();
      }
      const lipSyncData = await lipSyncAnalyzerRef.current.analyzeLipSync(audioBlob);
      return lipSyncData.frames;
    } catch {
      clearLipSyncTimers();
      return null;
    }
  }, [clearLipSyncTimers]);

  const stopPlayback = useCallback(
    (completeTurn: boolean) => {
      cancelFastFiller();
      stopAudioPlayback(audioQueueRef, mobileAudioServiceRef, onVisemeControl);
      cleanupAudioPlayback();

      if (completeTurn) {
        completeAssistantTurn();
      }
    },
    [
      cancelFastFiller,
      cleanupAudioPlayback,
      completeAssistantTurn,
      onVisemeControl,
    ],
  );

  const playAssistantAudio = useCallback(
    async (audioBase64: string, metadataForPlayback?: VoiceInterfaceMetadata | null) => {
      cancelFastFiller();
      if (isMuted) {
        voiceController.notifySpeaking();
        onAssistantPlaybackStart?.({ metadata: metadataForPlayback ?? null });
        window.setTimeout(() => {
          completeAssistantTurn();
        }, 240);
        return;
      }

      if (deferForIOSAudioUnlock({
        audioBase64,
        metadata: metadataForPlayback ?? null,
      })) {
        return;
      }

      let audioBytes: Uint8Array;
      try {
        audioBytes = Uint8Array.from(atob(audioBase64), (char) => char.charCodeAt(0));
      } catch (decodeError) {
        console.error('Audio decode failed:', decodeError);
        playAudioFallbackNotice();
        completeAssistantTurn(true);
        return;
      }
      const detectedFormat = AudioDataProcessor.detectAudioFormat(audioBytes.buffer as ArrayBuffer);
      const audioBlob = new Blob([audioBytes], { type: detectedFormat });
      const audioUrl = URL.createObjectURL(audioBlob);
      const audioService = ensureAudioService();

      revokeAudioUrl();
      audioUrlRef.current = audioUrl;

      let lipSyncFrames: LipSyncFrame[] | null = null;
      if (!metadataForPlayback?.vrm_control && onVisemeControl) {
        try {
          if (!lipSyncAnalyzerRef.current) {
            lipSyncAnalyzerRef.current = new LipSyncAnalyzer();
          }
          lipSyncFrames = await analyzeLipSyncFrames(audioBlob);
        } catch {
          clearLipSyncTimers();
          lipSyncFrames = null;
        }
      }

      setLoadingMessage(LOADING_LABELS[currentLanguage].speaking);
      setLoadingPhase('tts');
      voiceController.notifySpeaking();

      audioService.updateEventHandlers({
        onPlay: () => {
          onAssistantPlaybackStart?.({ metadata: metadataForPlayback ?? null });
          if (lipSyncFrames && lipSyncFrames.length > 0) {
            scheduleLipSyncFrames(lipSyncFrames);
          }
        },
        onEnded: () => {
          cleanupAudioPlayback();
          completeAssistantTurn();
        },
        onError: (playbackError) => {
          cleanupAudioPlayback();
          setError(formatError(playbackError, currentLanguage));
          playAudioFallbackNotice();
          completeAssistantTurn(true);
        },
      });

      const result = await audioService.playAudio(audioBlob);
      if (!result.success) {
        cleanupAudioPlayback();
        playAudioFallbackNotice();
        completeAssistantTurn(true);
        throw result.error ?? new Error('音声再生に失敗しました');
      }
    },
    [
      cleanupAudioPlayback,
      cancelFastFiller,
      clearLipSyncTimers,
      completeAssistantTurn,
      currentLanguage,
      analyzeLipSyncFrames,
      deferForIOSAudioUnlock,
      ensureAudioService,
      isMuted,
      onAssistantPlaybackStart,
      onVisemeControl,
      playAudioFallbackNotice,
      revokeAudioUrl,
      scheduleLipSyncFrames,
      setError,
      setLoadingMessage,
      setLoadingPhase,
      voiceController,
    ],
  );

  const unlockAudioPlayback = useCallback((): boolean => {
    if (sessionState === 'listening') {
      return false;
    }

    const pendingPlayback = pendingIOSPlaybackRef.current;
    if (!pendingPlayback || isReplayingPendingIOSAudioRef.current) {
      return false;
    }

    pendingIOSPlaybackRef.current = null;
    isReplayingPendingIOSAudioRef.current = true;
    const replayToken = pendingIOSPlaybackReplayTokenRef.current + 1;
    pendingIOSPlaybackReplayTokenRef.current = replayToken;
    setError(null);

    void (async () => {
      try {
        await AudioInteractionManager.getInstance().forceInitialize();
        if (pendingIOSPlaybackReplayTokenRef.current !== replayToken) {
          return;
        }
        await playAssistantAudio(pendingPlayback.audioBase64, pendingPlayback.metadata);
      } catch (error) {
        if (pendingIOSPlaybackReplayTokenRef.current !== replayToken) {
          return;
        }
        if (isAudioGestureRequiredError(error)) {
          pendingIOSPlaybackRef.current = pendingPlayback;
          setError(getTapToEnableAudioMessage(currentLanguage));
        } else {
          setError(formatError(error, currentLanguage));
        }
      } finally {
        if (pendingIOSPlaybackReplayTokenRef.current === replayToken) {
          isReplayingPendingIOSAudioRef.current = false;
        }
      }
    })();

    return true;
  }, [currentLanguage, playAssistantAudio, sessionState, setError]);

  const cancelPendingIOSPlaybackReplay = useCallback(() => {
    if (!pendingIOSPlaybackRef.current && !isReplayingPendingIOSAudioRef.current) {
      return;
    }

    pendingIOSPlaybackRef.current = null;
    isReplayingPendingIOSAudioRef.current = false;
    pendingIOSPlaybackReplayTokenRef.current += 1;
  }, []);

  const resetFallbackNoticeCount = useCallback(() => {
    fallbackNoticeCountRef.current = 0;
  }, []);

  useEffect(() => {
    return () => {
      pendingIOSPlaybackRef.current = null;
      isReplayingPendingIOSAudioRef.current = false;
      pendingIOSPlaybackReplayTokenRef.current += 1;
      cancelFastFiller();
      cleanupAudioPlayback();
      lipSyncAnalyzerRef.current?.dispose();
      mobileAudioServiceRef.current?.dispose();
    };
  }, [cancelFastFiller, cleanupAudioPlayback]);

  return {
    audioQueueRef,
    mobileAudioServiceRef,
    clearLipSyncTimers,
    cleanupAudioPlayback,
    analyzeLipSyncFrames,
    scheduleLipSyncFrames,
    stopPlayback,
    playAssistantAudio,
    playAudioFallbackNotice,
    deferForIOSAudioUnlock,
    unlockAudioPlayback,
    cancelPendingIOSPlaybackReplay,
    resetFallbackNoticeCount,
  };
}

'use client';

import { unlockAudioForUserGesture } from '@/lib/audio/audio-interaction-manager';
import {
  startSensorPolling,
  stopSensorPolling,
  type DeviceDetectionEvent,
} from '@/lib/api/device-webhook';
import { getStageBackgroundStyle } from '@/lib/get-stage-background-style';
import { overlayLabels } from '@/lib/kiosk-labels';
import { getMemberCardPhase2ReceptionMessage } from '@/lib/member-card-reception';
import {
  applyVrmAssistantSpeakingPose,
  applyVrmThinkingPose,
} from '@/lib/emotion-manager';
import {
  KIOSK_IDLE_MS,
  KIOSK_DEVICE_WELCOME_COOLDOWN_MS,
  KIOSK_WELCOME_COOLDOWN_MS,
  type KioskMicMode,
  type KioskPhase,
  type KioskTriggerMode,
  readKioskMicMode,
  readKioskTriggerMode,
} from '@/lib/kiosk-constants';
import { getDefaultKioskLanguage } from '@/lib/env-client';
import { Settings } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import type { CharacterAnimationData } from './utils/character-animation-utils';
import type { BackgroundOption } from './components/BackgroundSelector';
import {
  formatMemberNumberSuccess,
  kioskVoiceModeBadgeLabel,
  type WelcomeTriggerSource,
} from './utils/kiosk-page-helpers';
import { useKioskViewportLock } from './hooks/useKioskViewportLock';
import CharacterAvatar from './components/CharacterAvatar';
import {
  ConversationHistoryEffects,
  type ConversationHistoryItem,
} from './components/ConversationHistoryEffects';
import { KioskBottomBar } from './components/KioskBottomBar';
import { KioskOcrOverlay } from './components/KioskOcrOverlay';
import { KioskSettingsOverlay } from './components/KioskSettingsOverlay';
import { KioskSlideOverlay } from './components/KioskSlideOverlay';
import { KioskWelcomeOverlay } from './components/KioskWelcomeOverlay';
import { RestroomRouteOverlay } from './components/RestroomRouteOverlay';
import { SlideLanguagePicker } from './components/SlideLanguagePicker';
import InitialSettingsModal from './components/InitialSettingsModal';
import ClockBadge from './components/ClockBadge';
import type { SettingsPanelPropsFromSource } from './components/SettingsPanel';
import VoiceInterface, { type VoiceInterfaceMetadata } from './components/VoiceInterface';
import type { OcrResponse } from '@/lib/api/ocr-api';
import { startReception } from '@/lib/reception-api';
import { cancelSttWarmup, sendSttWarmup } from '@/lib/stt-warmup';

function RestroomRouteTrigger({ response, onTrigger }: { response: string, onTrigger: () => void }) {
  const lastResponseRef = useRef(response);
  useEffect(() => {
    if (response && response !== lastResponseRef.current) {
      lastResponseRef.current = response;
      if (/(toilet|restroom|トイレ|お手洗い|洗手间|화장실)/i.test(response)) {
        onTrigger();
      }
    }
  }, [response, onTrigger]);
  return null;
}

export default function Home() {
  useKioskViewportLock();

  const [kioskPhase, setKioskPhase] = useState<KioskPhase>('notice');
  const kioskPhaseRef = useRef<KioskPhase>('notice');
  const [kioskVoiceLocked, setKioskVoiceLocked] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>(getDefaultKioskLanguage());
  const [triggerMode, setTriggerMode] = useState<KioskTriggerMode>('screen');
  const [micInputMode, setMicInputMode] = useState<KioskMicMode>('toggle');

  // Hydration-safe: read localStorage only on client after mount
  useEffect(() => {
    setTriggerMode(readKioskTriggerMode());
    setMicInputMode(readKioskMicMode());
  }, []);
  const [ocrMode, setOcrMode] = useState<'member_card' | 'handwriting'>('member_card');
  const [welcomeMemberOcrOpen, setWelcomeMemberOcrOpen] = useState(false);
  const [welcomeMemberOcrSessionKey, setWelcomeMemberOcrSessionKey] = useState(0);
  const [ocrStatus, setOcrStatus] = useState<{
    kind: 'member_card' | 'handwriting' | 'error';
    text: string;
    visibleUntil: number;
  } | null>(null);
  const [characterBackground, setCharacterBackground] = useState<BackgroundOption>({
    id: 'engineer-cafe-bg',
    name: 'Engineer Cafe',
    type: 'image',
    value: '/backgrounds/IMG_5573.JPG',
  });
  const [lightingIntensity, setLightingIntensity] = useState(1);
  const [setVisemeFunction, setSetVisemeFunction] = useState<
    ((viseme: string, intensity: number) => void) | null
  >(null);
  const [setExpressionFunction, setSetExpressionFunction] = useState<
    ((expression: string, weight: number) => void) | null
  >(null);
  const [, setLatestMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [conversationHistory, setConversationHistory] = useState<ConversationHistoryItem[]>([]);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const settingsPanelPropsRef = useRef<SettingsPanelPropsFromSource | null>(null);
  const [settingsPanelProps, setSettingsPanelProps] =
    useState<SettingsPanelPropsFromSource | null>(null);
  const [presentationAutoStartKey, setPresentationAutoStartKey] = useState(0);
  const [presentationLanguage, setPresentationLanguage] = useState<'ja' | 'en'>('ja');
  const [showRestroomRoute, setShowRestroomRoute] = useState(false);
  const [slideLanguagePickerOpen, setSlideLanguagePickerOpen] = useState(false);
  const playKeyframeAnimationRef = useRef<((data: CharacterAnimationData) => void) | null>(null);
  const stopKeyframeAnimationRef = useRef<(() => void) | null>(null);
  const lastVrmControlPlayedRef = useRef<unknown>(null);
  const pendingVrmPlaybackRef = useRef<CharacterAnimationData | null>(null);
  const lastTranscriptRef = useRef<string>('');
  const lastResponseRef = useRef<string>('');
  const returnToIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kioskVisitCleanupRef = useRef<(() => void) | null>(null);
  const kioskPlayWelcomeRef = useRef<((source?: WelcomeTriggerSource) => Promise<void>) | null>(
    null,
  );
  const welcomeAutoListenStartRef = useRef<(() => Promise<boolean>) | null>(null);
  const pendingSensorWelcomeAutoListenRef = useRef(false);
  const prevTriggerModeRef = useRef<KioskTriggerMode>(triggerMode);
  const [welcomeCooldown, setWelcomeCooldown] = useState(false);
  const [welcomeCooldownUntilMs, setWelcomeCooldownUntilMs] = useState(0);
  const [welcomeCooldownRemainingMs, setWelcomeCooldownRemainingMs] = useState(0);
  const welcomeCooldownUntilRef = useRef(0);

  const showAvatarControls = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';

  const showWelcomeCooldownNotice = useCallback((): boolean => {
    const remainingMs = Math.max(0, welcomeCooldownUntilRef.current - Date.now());
    if (remainingMs <= 0) {
      return false;
    }

    setWelcomeCooldown(true);
    setWelcomeCooldownRemainingMs(remainingMs);
    return true;
  }, []);

  const armWelcomeCooldown = useCallback((cooldownMs: number): boolean => {
    if (showWelcomeCooldownNotice()) {
      return false;
    }

    const untilMs = Date.now() + cooldownMs;
    welcomeCooldownUntilRef.current = untilMs;
    setWelcomeCooldownUntilMs(untilMs);
    setWelcomeCooldown(true);
    setWelcomeCooldownRemainingMs(cooldownMs);
    return true;
  }, [showWelcomeCooldownNotice]);

  useEffect(() => {
    if (welcomeCooldownUntilMs <= 0) {
      return;
    }

    const tick = () => {
      const remainingMs = Math.max(0, welcomeCooldownUntilRef.current - Date.now());
      setWelcomeCooldownRemainingMs(remainingMs);
      if (remainingMs <= 0) {
        welcomeCooldownUntilRef.current = 0;
        setWelcomeCooldownUntilMs(0);
        setWelcomeCooldown(false);
      }
    };

    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [welcomeCooldownUntilMs]);

  useEffect(() => {
    kioskPhaseRef.current = kioskPhase;
  }, [kioskPhase]);

  const setKioskPhaseSynced = useCallback((nextPhase: KioskPhase) => {
    kioskPhaseRef.current = nextPhase;
    setKioskPhase(nextPhase);
  }, []);

  const clearReturnToIdleTimer = useCallback(() => {
    if (returnToIdleTimerRef.current !== null) {
      clearTimeout(returnToIdleTimerRef.current);
      returnToIdleTimerRef.current = null;
    }
  }, []);

  const resetConversationHistory = useCallback(() => {
    lastTranscriptRef.current = '';
    lastResponseRef.current = '';
    setConversationHistory([]);
  }, []);

  const returnToIdle = useCallback(() => {
    clearReturnToIdleTimer();
    pendingSensorWelcomeAutoListenRef.current = false;
    kioskVisitCleanupRef.current?.();
    setKioskPhaseSynced('idle');
  }, [clearReturnToIdleTimer, setKioskPhaseSynced]);

  const scheduleReturnToIdle = useCallback(() => {
    clearReturnToIdleTimer();
    returnToIdleTimerRef.current = setTimeout(() => {
      returnToIdleTimerRef.current = null;
      returnToIdle();
    }, KIOSK_IDLE_MS);
  }, [clearReturnToIdleTimer, returnToIdle]);

  const bumpUserActivity = useCallback(() => {
    const phase = kioskPhaseRef.current;
    if (phase === 'notice' || phase === 'idle') {
      return;
    }
    if (phase === 'slides') {
      clearReturnToIdleTimer();
      return;
    }
    scheduleReturnToIdle();
  }, [clearReturnToIdleTimer, scheduleReturnToIdle]);

  useEffect(() => {
    return () => {
      clearReturnToIdleTimer();
    };
  }, [clearReturnToIdleTimer]);

  const startOcrFromKioskAction = useCallback(
    (mode: 'member_card' | 'handwriting') => {
      pendingSensorWelcomeAutoListenRef.current = false;
      unlockAudioForUserGesture();
      clearReturnToIdleTimer();
      setWelcomeMemberOcrOpen(false);
      setOcrMode(mode);
      setKioskPhaseSynced('ocr');
    },
    [clearReturnToIdleTimer, setKioskPhaseSynced],
  );

  useEffect(() => {
    const onDeviceDetection = (event: Event) => {
      const detail = (event as CustomEvent<DeviceDetectionEvent>).detail;
      if (!detail) {
        return;
      }

      if (kioskPhaseRef.current !== 'idle') {
        if (detail.type === 'sensor_triggered') {
          showWelcomeCooldownNotice();
        }
        return;
      }

      if (detail.type === 'button_pressed') {
        const mode = detail.data?.mode;
        if (mode === 'member_card' || mode === 'handwriting') {
          startOcrFromKioskAction(mode);
        }
        return;
      }

      if (detail.type === 'sensor_triggered') {
        if (showWelcomeCooldownNotice()) {
          return;
        }
        void kioskPlayWelcomeRef.current?.('device');
      }
    };
    window.addEventListener('device-detection', onDeviceDetection);
    return () => {
      window.removeEventListener('device-detection', onDeviceDetection);
    };
  }, [showWelcomeCooldownNotice, startOcrFromKioskAction]);

  useEffect(() => {
    if (triggerMode === 'device' && kioskPhase !== 'notice' && kioskPhase !== 'slides') {
      startSensorPolling();
    } else {
      stopSensorPolling();
    }

    return () => {
      stopSensorPolling();
    };
  }, [kioskPhase, triggerMode]);

  useEffect(() => {
    if (kioskPhase === 'ocr' || kioskPhase === 'voice') {
      scheduleReturnToIdle();
    }
  }, [kioskPhase, scheduleReturnToIdle]);

  useEffect(() => {
    if (kioskPhase === 'slides') {
      setWelcomeMemberOcrOpen(false);
      setShowSettingsPanel(false);
    }
  }, [kioskPhase]);

  useEffect(() => {
    if (kioskPhase !== 'voice' && kioskVoiceLocked) {
      setKioskVoiceLocked(false);
    }
  }, [kioskPhase, kioskVoiceLocked]);

  const showKioskScreenChrome = triggerMode !== 'device';

  useEffect(() => {
    const previous = prevTriggerModeRef.current;
    prevTriggerModeRef.current = triggerMode;

    if (triggerMode !== 'device' || previous === 'device') {
      return;
    }
    if (kioskPhase === 'idle' || kioskPhase === 'notice') {
      return;
    }
    returnToIdle();
  }, [kioskPhase, returnToIdle, triggerMode]);

  const handleSettingsPanelPropsChange = useCallback(
    (props: SettingsPanelPropsFromSource) => {
      settingsPanelPropsRef.current = props;
      if (showSettingsPanel) {
        setSettingsPanelProps(props);
      }
    },
    [showSettingsPanel],
  );

  useEffect(() => {
    if (showSettingsPanel) {
      setSettingsPanelProps(settingsPanelPropsRef.current);
    } else {
      setSettingsPanelProps(null);
    }
  }, [showSettingsPanel]);

  const startPresentation = useCallback(
    (language: 'ja' | 'en') => {
      unlockAudioForUserGesture();
      clearReturnToIdleTimer();
      setSlideLanguagePickerOpen(false);
      setPresentationLanguage(language);
      setCurrentLanguage(language);
      setPresentationAutoStartKey((key) => key + 1);
      setKioskPhaseSynced('slides');

      window.setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent('autoStartPresentation', {
            detail: { autoPlay: true, language },
          }),
        );
      }, 150);
    },
    [clearReturnToIdleTimer, setKioskPhaseSynced],
  );

  const openSlideLanguagePicker = useCallback(() => {
    unlockAudioForUserGesture();
    clearReturnToIdleTimer();
    setSlideLanguagePickerOpen(true);
  }, [clearReturnToIdleTimer]);

  const handleCloseSlides = useCallback(() => {
    setSlideLanguagePickerOpen(false);
    returnToIdle();
  }, [returnToIdle]);

  return (
    <>
      <InitialSettingsModal
        language={currentLanguage}
        open={kioskPhase === 'notice'}
        onClose={() => setKioskPhaseSynced('idle')}
        onPreferencesSaved={(prefs) => {
          setCurrentLanguage(prefs.language);
          setTriggerMode(prefs.triggerMode);
          setMicInputMode(prefs.micMode);
        }}
      />
      <VoiceInterface
        language={currentLanguage}
        onLanguageChange={setCurrentLanguage}
        wakeWordEnabled={false}
        autoResumeListeningAfterAssistant={false}
        onVisemeControl={setVisemeFunction}
        showDefaultUI={false}
        onMetadataChange={(metadata) => {
          setLatestMetadata(metadata);
        }}
        onSlideAgentResponse={() => {
          startPresentation(currentLanguage);
        }}
        onAssistantPlaybackEnd={() => {
          // 音声再生終了時にキーフレームアニメーションを停止し、口を閉じる。
          // アニメーション duration は音声より長いため、放置すると
          // 回答終了後も口が動き続ける（実機検証で確認）。
          stopKeyframeAnimationRef.current?.();
          if (pendingSensorWelcomeAutoListenRef.current && kioskPhaseRef.current === 'voice') {
            pendingSensorWelcomeAutoListenRef.current = false;
            clearReturnToIdleTimer();
            void (async () => {
              const started = await welcomeAutoListenStartRef.current?.();
              if (!started && kioskPhaseRef.current === 'voice') {
                scheduleReturnToIdle();
              }
            })();
            return;
          }
          if (kioskPhaseRef.current === 'voice') {
            scheduleReturnToIdle();
          }
        }}
        onAssistantPlaybackStart={({ metadata: playbackMetadata }) => {
          const vc = playbackMetadata?.vrm_control;
          if (!vc) {
            return;
          }
          if (playKeyframeAnimationRef.current) {
            if (lastVrmControlPlayedRef.current !== vc) {
              lastVrmControlPlayedRef.current = vc;
              playKeyframeAnimationRef.current(vc);
            }
            pendingVrmPlaybackRef.current = null;
          } else {
            pendingVrmPlaybackRef.current = vc;
          }
        }}
        onVoiceTurnThinkingVisual={() => {
          applyVrmThinkingPose(setExpressionFunction ?? undefined);
        }}
        onVoiceTurnAssistantSpeakingVisual={() => {
          applyVrmAssistantSpeakingPose(setExpressionFunction ?? undefined);
        }}
      >
        {(voice) => {
          welcomeAutoListenStartRef.current = async () => {
            clearReturnToIdleTimer();
            setKioskVoiceLocked(true);
            const started = await voice.startListening();
            if (!started) {
              setKioskVoiceLocked(false);
            }
            return started;
          };
          kioskVisitCleanupRef.current = () => {
            cancelSttWarmup();
            voice.clearVisitState();
            setKioskVoiceLocked(false);
            pendingSensorWelcomeAutoListenRef.current = false;
            setWelcomeMemberOcrOpen(false);
            setOcrStatus(null);
            resetConversationHistory();
          };
          const labels = overlayLabels[voice.currentLanguage];
          const receptionTriggerType =
            triggerMode === 'device' ? 'sensor_trigger' : 'button_press';
          kioskPlayWelcomeRef.current = async (source: WelcomeTriggerSource = 'screen') => {
            const isDeviceTriggered = source === 'device';
            const cooldownMs = isDeviceTriggered
              ? KIOSK_DEVICE_WELCOME_COOLDOWN_MS
              : KIOSK_WELCOME_COOLDOWN_MS;
            if (!armWelcomeCooldown(cooldownMs)) {
              return;
            }
            pendingSensorWelcomeAutoListenRef.current = isDeviceTriggered;
            unlockAudioForUserGesture();
            sendSttWarmup({ language: voice.currentLanguage, sessionId: voice.sessionId });
            clearReturnToIdleTimer();
            setWelcomeMemberOcrOpen(false);
            setKioskPhaseSynced('voice');
            setKioskVoiceLocked(micInputMode !== 'push_to_talk');
            try {
              const result = await startReception({
                session_id: voice.sessionId,
                language: voice.currentLanguage,
                trigger_type: receptionTriggerType,
              });
              await voice.speakPreparedText(result.greeting, null);
            } catch {
              const fallback =
                voice.currentLanguage === 'ja'
                  ? 'エンジニアカフェへようこそ。ご用件をお聞かせください。'
                  : 'Welcome to Engineer Cafe. How can I help you today?';
              await voice.speakPreparedText(fallback, null);
            } finally {
              scheduleReturnToIdle();
            }
          };
          const showSlideMode = kioskPhase === 'slides';
          const stageBackgroundStyle = getStageBackgroundStyle(characterBackground);

          const screenPadding = {
            paddingTop: showSlideMode
              ? 'max(0.25rem, env(safe-area-inset-top))'
              : 'max(1.5rem, env(safe-area-inset-top))',
            paddingBottom: showSlideMode
              ? 'max(0.25rem, env(safe-area-inset-bottom))'
              : 'max(1.5rem, env(safe-area-inset-bottom))',
            paddingLeft: showSlideMode
              ? 'max(0.25rem, env(safe-area-inset-left))'
              : 'max(1.5rem, env(safe-area-inset-left))',
            paddingRight: showSlideMode
              ? 'max(0.25rem, env(safe-area-inset-right))'
              : 'max(1.5rem, env(safe-area-inset-right))',
          } satisfies CSSProperties;


          const characterCameraOffset = { x: 0, y: 0, z: 0 };
          // Sakura's neutral VRM root renders slightly left at x=0. Keep this
          // single parent offset so every session state and animation stays centered.
          const characterModelOffset = { x: 0.15, y: 0, z: 0 };
          const characterRotationOffset = { x: 0, y: -0.2, z: 0 };

          const setOcrStatusMessage = (
            kind: 'member_card' | 'handwriting' | 'error',
            text: string,
          ) => {
            setOcrStatus({
              kind,
              text,
              visibleUntil: Date.now() + 5000,
            });
          };

          const startMemberCardReceptionFromOcr = async (result: OcrResponse) => {
            clearReturnToIdleTimer();
            setWelcomeMemberOcrOpen(false);

            const memberNumber = result.member_number;
            if (memberNumber === null) {
              returnToIdle();
              setOcrStatusMessage('error', labels.ocrReadFailed);
              return;
            }

            setOcrStatusMessage(
              'member_card',
              formatMemberNumberSuccess(labels, memberNumber),
            );
            setKioskPhaseSynced('voice');
            setKioskVoiceLocked(micInputMode !== 'push_to_talk');
            sendSttWarmup({ language: voice.currentLanguage, sessionId: voice.sessionId });
            const phase2Notice = getMemberCardPhase2ReceptionMessage(
              memberNumber,
              voice.currentLanguage,
            );

            try {
              await startReception({
                session_id: voice.sessionId,
                language: voice.currentLanguage,
                trigger_type: receptionTriggerType,
              });
              await voice.speakPreparedText(phase2Notice, null);
            } catch {
              await voice.speakPreparedText(phase2Notice, null);
            } finally {
              scheduleReturnToIdle();
            }
          };

          const handleOcrSuccess = (result: OcrResponse) => {
            clearReturnToIdleTimer();

            if (result.mode === 'member_card') {
              void startMemberCardReceptionFromOcr(result);
              return;
            }

            const recognized = (result.recognized_text ?? '').trim();
            if (!recognized) {
              returnToIdle();
              setOcrStatusMessage('error', labels.ocrReadFailed);
              return;
            }

            setOcrStatus(null);
            setKioskVoiceLocked(false);
            setKioskPhaseSynced('voice');
            void voice.sendMessage(recognized);
          };

          const handleWelcomeMemberOcrSuccess = (result: OcrResponse) => {
            void startMemberCardReceptionFromOcr(result);
          };

          const handleWelcomeMemberOcrEndSilent = () => {
            setWelcomeMemberOcrOpen(false);
          };

          return (
            <>
              <RestroomRouteTrigger response={voice.response} onTrigger={() => setShowRestroomRoute(true)} />
              <ConversationHistoryEffects
                transcript={voice.transcript}
                response={voice.response}
                lastTranscriptRef={lastTranscriptRef}
                lastResponseRef={lastResponseRef}
                setConversationHistory={setConversationHistory}
              />
              <main data-testid="kiosk-viewport-root" className="kiosk-viewport-root">
                {(kioskPhase === 'voice' || kioskPhase === 'idle') && (
                  <div
                    className="pointer-events-none absolute left-1/2 top-[max(0.5rem,env(safe-area-inset-top))] z-[38] max-w-[92vw] -translate-x-1/2 truncate rounded-full border border-white/25 bg-black/55 px-4 py-1.5 text-center text-[11px] font-semibold text-white shadow-md backdrop-blur-md sm:text-xs"
                    data-testid="kiosk-voice-mode-badge"
                  >
                    {kioskVoiceModeBadgeLabel(voice, labels)}
                  </div>
                )}
                <div className="absolute inset-0 -z-10" style={stageBackgroundStyle}>
                  <CharacterAvatar
                    modelPath="/characters/models/sakura.vrm"
                    sessionState={voice.sessionState}
                    background={characterBackground}
                    lightingIntensity={lightingIntensity}
                    cameraPositionOffset={characterCameraOffset}
                    modelPositionOffset={characterModelOffset}
                    modelRotationOffset={characterRotationOffset}
                    enableClickAnimation={!showSlideMode}
                    showControls={showAvatarControls && !showSlideMode && kioskPhase === 'voice'}
                    volume={Math.round(voice.volume * 100)}
                    isMuted={voice.isMuted}
                    onVolumeChange={(value) => voice.setVolume(value / 100)}
                    onMuteToggle={() => voice.setMuted(!voice.isMuted)}
                    onVisemeControl={(setViseme) => {
                      setSetVisemeFunction(() => setViseme);
                    }}
                    onExpressionControl={(setExpression) => {
                      setSetExpressionFunction(() => setExpression);
                    }}
                    onKeyframeAnimationControl={({ play, stop }) => {
                      playKeyframeAnimationRef.current = play;
                      stopKeyframeAnimationRef.current = stop;
                      const pending = pendingVrmPlaybackRef.current;
                      if (pending && lastVrmControlPlayedRef.current !== pending) {
                        lastVrmControlPlayedRef.current = pending;
                        play(pending);
                        pendingVrmPlaybackRef.current = null;
                      }
                    }}
                    onBackgroundChange={setCharacterBackground}
                    onLightingChange={setLightingIntensity}
                    settingsPanelPropsRef={settingsPanelPropsRef}
                    onSettingsPanelPropsChange={handleSettingsPanelPropsChange}
                  />
                </div>

                {!showSlideMode ? (
                  <div className="pointer-events-none absolute inset-0 z-30">
                    <div
                      className="pointer-events-none absolute"
                      style={{
                        top: screenPadding.paddingTop,
                        left: screenPadding.paddingLeft,
                      }}
                    >
                      <ClockBadge language={voice.currentLanguage} />
                    </div>
                    <div
                      className="pointer-events-auto absolute"
                      style={{
                        top: screenPadding.paddingTop,
                        right: screenPadding.paddingRight,
                      }}
                    >
                      <button
                        data-testid="kiosk-settings-button"
                        type="button"
                        onClick={() => setShowSettingsPanel(true)}
                        aria-label={voice.currentLanguage === 'ja' ? '設定' : 'Settings'}
                        className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-white/15 bg-black/45 text-white shadow-lg backdrop-blur-md transition-transform duration-200 ease-out hover:scale-105"
                      >
                        <Settings className="size-5" />
                      </button>
                    </div>
                  </div>
                ) : null}

                <KioskWelcomeOverlay
                  open={welcomeMemberOcrOpen}
                  welcomeMemberOcrSessionKey={welcomeMemberOcrSessionKey}
                  kioskPhase={kioskPhase}
                  showSlideMode={showSlideMode}
                  labels={labels}
                  sessionId={voice.sessionId}
                  bumpUserActivity={bumpUserActivity}
                  onMemberOcrSuccess={handleWelcomeMemberOcrSuccess}
                  onMemberOcrEnd={handleWelcomeMemberOcrEndSilent}
                />

                <KioskSettingsOverlay
                  open={showSettingsPanel}
                  settingsPanelProps={settingsPanelProps}
                  showSlideMode={showSlideMode}
                  screenPadding={screenPadding}
                  labels={labels}
                  conversationHistory={conversationHistory}
                  voice={voice}
                  triggerMode={triggerMode}
                  micInputMode={micInputMode}
                  setCurrentLanguage={setCurrentLanguage}
                  setTriggerMode={setTriggerMode}
                  setMicInputMode={setMicInputMode}
                  onClose={() => setShowSettingsPanel(false)}
                  onOpenSlides={openSlideLanguagePicker}
                  onCloseSlides={handleCloseSlides}
                />

                {(kioskPhase === 'idle' || kioskPhase === 'voice' || kioskPhase === 'notice') && (
                  <KioskBottomBar
                    kioskPhase={kioskPhase}
                    setKioskPhase={setKioskPhase}
                    kioskVoiceLocked={kioskVoiceLocked}
                    setKioskVoiceLocked={setKioskVoiceLocked}
                    micInputMode={micInputMode}
                    showKioskScreenChrome={showKioskScreenChrome}
                    welcomeCooldown={welcomeCooldown}
                    welcomeCooldownRemainingMs={welcomeCooldownRemainingMs}
                    labels={labels}
                    ocrStatus={ocrStatus}
                    voice={voice}
                    onPlayWelcome={() => kioskPlayWelcomeRef.current?.('screen')}
                    onStartPresentation={openSlideLanguagePicker}
                    clearReturnToIdleTimer={clearReturnToIdleTimer}
                    setWelcomeMemberOcrOpen={setWelcomeMemberOcrOpen}
                    setOcrMode={setOcrMode}
                  />
                )}

                <RestroomRouteOverlay
                  visible={showRestroomRoute}
                  language={voice.currentLanguage}
                  onClose={() => setShowRestroomRoute(false)}
                  bumpUserActivity={bumpUserActivity}
                />

                <KioskOcrOverlay
                  visible={kioskPhase === 'ocr'}
                  ocrMode={ocrMode}
                  labels={labels}
                  sessionId={voice.sessionId}
                  bumpUserActivity={bumpUserActivity}
                  onSuccess={handleOcrSuccess}
                  onFallback={() => {
                    returnToIdle();
                    setOcrStatusMessage('error', labels.ocrReadFailed);
                  }}
                  onSkip={() => {
                    returnToIdle();
                  }}
                  onBackToIdle={() => {
                    returnToIdle();
                  }}
                />

                {slideLanguagePickerOpen && !showSlideMode ? (
                  <SlideLanguagePicker
                    language={voice.currentLanguage}
                    onClose={() => setSlideLanguagePickerOpen(false)}
                    onStartPresentation={startPresentation}
                  />
                ) : null}

                <KioskSlideOverlay
                  open={showSlideMode}
                  screenPadding={screenPadding}
                  labels={labels}
                  language={presentationLanguage}
                  autoStartKey={presentationAutoStartKey}
                  sessionId={voice.sessionId}
                  volume={Math.round(voice.volume * 100)}
                  onClose={handleCloseSlides}
                  onPointerActivity={bumpUserActivity}
                  onVisemeControl={setVisemeFunction}
                  onExpressionControl={setExpressionFunction}
                  onPresentationComplete={() => {
                    if (kioskPhaseRef.current === 'slides') {
                      scheduleReturnToIdle();
                    }
                  }}
                />
              </main>
            </>
          );
        }}
      </VoiceInterface>
    </>
  );
}

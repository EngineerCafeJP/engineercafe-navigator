'use client';

import { unlockAudioForUserGesture } from '@/lib/audio/audio-interaction-manager';
import { startSensorPolling, stopSensorPolling } from '@/lib/api/device-webhook';
import { getStageBackgroundStyle } from '@/lib/get-stage-background-style';
import { overlayLabels } from '@/lib/kiosk-labels';
import {
  applyVrmAssistantSpeakingPose,
  applyVrmThinkingPose,
} from '@/lib/emotion-manager';
import {
  KIOSK_IDLE_MS,
  KIOSK_WELCOME_COOLDOWN_MS,
  type KioskMicMode,
  type KioskPhase,
  type KioskTriggerMode,
  readKioskMicMode,
  readKioskTriggerMode,
  writeKioskMicMode,
  writeKioskTriggerMode,
} from '@/lib/kiosk-constants';
import { cn } from '@/lib/cn';
import { Languages, Settings, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import type { CharacterAnimationData } from './utils/character-animation-utils';
import type { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import {
  ConversationHistoryEffects,
  type ConversationHistoryItem,
} from './components/ConversationHistoryEffects';
import { KioskBottomBar } from './components/KioskBottomBar';
import { KioskOcrOverlay } from './components/KioskOcrOverlay';
import { KioskWelcomeOverlay } from './components/KioskWelcomeOverlay';
import InitialSettingsModal from './components/InitialSettingsModal';
import ReceptionPdfGuide from './components/ReceptionPdfGuide';
import ClockBadge from './components/ClockBadge';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './components/SettingsPanel';
import VoiceInterface, {
  type VoiceInterfaceMetadata,
  type VoiceInterfaceRenderProps,
} from './components/VoiceInterface';
import type { OcrResponse } from '@/lib/api/ocr-api';
import { startReception } from '@/lib/reception-api';
import { cancelSttWarmup, sendSttWarmup } from '@/lib/stt-warmup';

function kioskVoiceModeBadgeLabel(
  voice: VoiceInterfaceRenderProps,
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'],
): string {
  if (voice.sessionState === 'listening') {
    return labels.voiceModeListening;
  }
  if (voice.loadingPhase === 'stt') {
    return labels.voiceModeStt;
  }
  if (voice.loadingPhase === 'tts') {
    return labels.voiceModeTts;
  }
  if (voice.sessionState === 'speaking') {
    return labels.voiceModeSpeaking;
  }
  if (voice.loadingPhase === 'llm') {
    return labels.voiceModeLlm;
  }
  if (voice.sessionState === 'processing') {
    return labels.voiceModeLlm;
  }
  if (voice.isLoading && voice.loadingPhase === 'mic') {
    return labels.voiceModeStt;
  }
  return labels.voiceModeIdle;
}


export default function Home() {
  const [kioskPhase, setKioskPhase] = useState<KioskPhase>('notice');
  const kioskPhaseRef = useRef<KioskPhase>('notice');
  const [kioskVoiceLocked, setKioskVoiceLocked] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>('ja');
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
  const [slideLanguagePickerOpen, setSlideLanguagePickerOpen] = useState(false);
  const playKeyframeAnimationRef = useRef<((data: CharacterAnimationData) => void) | null>(null);
  const lastVrmControlPlayedRef = useRef<unknown>(null);
  const pendingVrmPlaybackRef = useRef<CharacterAnimationData | null>(null);
  const lastTranscriptRef = useRef<string>('');
  const lastResponseRef = useRef<string>('');
  const returnToIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kioskVisitCleanupRef = useRef<(() => void) | null>(null);
  const kioskPlayWelcomeRef = useRef<(() => Promise<void>) | null>(null);
  const prevTriggerModeRef = useRef<KioskTriggerMode>(triggerMode);
  const welcomeCooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const welcomeCooldownActiveRef = useRef(false);
  const [welcomeCooldown, setWelcomeCooldown] = useState(false);

  const showAvatarControls = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';

  const armWelcomeCooldown = useCallback((): boolean => {
    if (welcomeCooldownActiveRef.current) {
      return false;
    }
    welcomeCooldownActiveRef.current = true;
    setWelcomeCooldown(true);
    if (welcomeCooldownTimerRef.current !== null) {
      clearTimeout(welcomeCooldownTimerRef.current);
    }
    welcomeCooldownTimerRef.current = setTimeout(() => {
      welcomeCooldownTimerRef.current = null;
      welcomeCooldownActiveRef.current = false;
      setWelcomeCooldown(false);
    }, KIOSK_WELCOME_COOLDOWN_MS);
    return true;
  }, []);

  useEffect(() => {
    return () => {
      if (welcomeCooldownTimerRef.current !== null) {
        clearTimeout(welcomeCooldownTimerRef.current);
      }
    };
  }, []);

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

  useEffect(() => {
    const onDeviceDetection = () => {
      if (kioskPhaseRef.current !== 'idle') {
        return;
      }
      void kioskPlayWelcomeRef.current?.();
    };
    window.addEventListener('device-detection', onDeviceDetection);
    return () => {
      window.removeEventListener('device-detection', onDeviceDetection);
    };
  }, []);

  useEffect(() => {
    if (triggerMode === 'device' && kioskPhase === 'idle') {
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

  const isSlideAgentMetadata = useCallback((metadata: VoiceInterfaceMetadata | null): boolean => {
    if (!metadata) {
      return false;
    }
    return (
      metadata.agent === 'SlideAgent' ||
      metadata.route === 'slide' ||
      metadata.reception_target_agent === 'slide_agent' ||
      metadata.reception_target_agent === 'SlideAgent'
    );
  }, []);

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
        autoResumeListeningAfterAssistant={
          micInputMode === 'push_to_talk' ? false : kioskVoiceLocked
        }
        onVisemeControl={setVisemeFunction}
        showDefaultUI={false}
        onMetadataChange={(metadata) => {
          setLatestMetadata(metadata);
          if (isSlideAgentMetadata(metadata)) {
            startPresentation(currentLanguage);
          }
        }}
        onSlideAgentResponse={() => {
          startPresentation(currentLanguage);
        }}
        onAssistantPlaybackEnd={() => {
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
          kioskVisitCleanupRef.current = () => {
            cancelSttWarmup();
            voice.clearVisitState();
            setKioskVoiceLocked(false);
            setWelcomeMemberOcrOpen(false);
            setOcrStatus(null);
            resetConversationHistory();
          };
          const labels = overlayLabels[voice.currentLanguage];
          const receptionTriggerType =
            triggerMode === 'device' ? 'sensor_trigger' : 'button_press';
          kioskPlayWelcomeRef.current = async () => {
            if (!armWelcomeCooldown()) {
              return;
            }
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

          const handleOcrSuccess = (result: OcrResponse) => {
            clearReturnToIdleTimer();

            if (result.mode === 'member_card') {
              returnToIdle();
              if (result.member_number === null) {
                setOcrStatusMessage('error', labels.ocrReadFailed);
              }
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
            clearReturnToIdleTimer();
            returnToIdle();
            if (result.member_number === null) {
              setOcrStatusMessage('error', labels.ocrReadFailed);
            }
          };

          const handleWelcomeMemberOcrEndSilent = () => {
            setWelcomeMemberOcrOpen(false);
          };

          return (
            <>
              <ConversationHistoryEffects
                transcript={voice.transcript}
                response={voice.response}
                lastTranscriptRef={lastTranscriptRef}
                lastResponseRef={lastResponseRef}
                setConversationHistory={setConversationHistory}
              />
              <main className="relative h-[100svh] w-screen overflow-hidden">
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
                    onKeyframeAnimationControl={(play) => {
                      playKeyframeAnimationRef.current = play;
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

                {showSettingsPanel && settingsPanelProps ? (
                  <div
                    className="absolute inset-0 z-40 pointer-events-none"
                    aria-hidden={!showSettingsPanel}
                  >
                    <div
                      className="pointer-events-auto absolute top-0 flex max-h-full justify-end"
                      style={{
                        top: screenPadding.paddingTop,
                        right: screenPadding.paddingRight,
                      }}
                    >
                      <SettingsPanel
                        {...settingsPanelProps}
                        kiosk_language={voice.currentLanguage}
                        kiosk_trigger_mode={triggerMode}
                        kiosk_mic_mode={micInputMode}
                        on_kiosk_language_change={(language) => {
                          setCurrentLanguage(language);
                        }}
                        on_kiosk_trigger_mode_change={(mode) => {
                          setTriggerMode(mode);
                          writeKioskTriggerMode(mode);
                        }}
                        on_kiosk_mic_mode_change={(mode) => {
                          setMicInputMode(mode);
                          writeKioskMicMode(mode);
                        }}
                        volume={Math.round(voice.volume * 100)}
                        is_muted={voice.isMuted}
                        on_volume_change={(value) => {
                          voice.setVolume(value / 100);
                        }}
                        on_mute_toggle={() => {
                          voice.setMuted(!voice.isMuted);
                        }}
                        show_close_button
                        on_close={() => setShowSettingsPanel(false)}
                        extra_tab={{
                          label: voice.currentLanguage === 'ja' ? '会話履歴' : 'Conversation',
                          content: (
                            <div className="space-y-2 overflow-y-auto pr-1">
                              {conversationHistory.length === 0 ? (
                                <p className="text-sm text-gray-600">{labels.helperPrompt}</p>
                              ) : (
                                conversationHistory.map((item) => (
                                  <div
                                    key={item.id}
                                    className={cn(
                                      'rounded-2xl px-3 py-2 text-sm leading-6',
                                      item.role === 'user'
                                        ? 'bg-gray-100 text-gray-800'
                                        : 'bg-blue-50 text-gray-800',
                                    )}
                                  >
                                    <p className="text-xs font-medium text-gray-500">
                                      {item.role === 'user'
                                        ? voice.currentLanguage === 'ja'
                                          ? 'あなた'
                                          : 'You'
                                        : 'Navigator'}
                                    </p>
                                    <p className="mt-1 whitespace-pre-wrap">{item.text}</p>
                                  </div>
                                ))
                              )}
                            </div>
                          ),
                        }}
                        slide_mode_open={showSlideMode}
                        on_open_slides={openSlideLanguagePicker}
                        on_close_slides={handleCloseSlides}
                        open_slides_label={labels.openSlides}
                        close_slides_label={labels.closeSlides}
                      />
                    </div>
                  </div>
                ) : null}

                {(kioskPhase === 'idle' || kioskPhase === 'voice' || kioskPhase === 'notice') && (
                  <KioskBottomBar
                    kioskPhase={kioskPhase}
                    setKioskPhase={setKioskPhase}
                    kioskVoiceLocked={kioskVoiceLocked}
                    setKioskVoiceLocked={setKioskVoiceLocked}
                    micInputMode={micInputMode}
                    showKioskScreenChrome={showKioskScreenChrome}
                    welcomeCooldown={welcomeCooldown}
                    labels={labels}
                    ocrStatus={ocrStatus}
                    voice={voice}
                    onPlayWelcome={() => kioskPlayWelcomeRef.current?.()}
                    onStartPresentation={openSlideLanguagePicker}
                    clearReturnToIdleTimer={clearReturnToIdleTimer}
                    setWelcomeMemberOcrOpen={setWelcomeMemberOcrOpen}
                    setOcrMode={setOcrMode}
                  />
                )}

                <KioskOcrOverlay
                  visible={kioskPhase === 'ocr' && showKioskScreenChrome}
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
                  <div className="pointer-events-auto absolute inset-0 z-50 flex items-center justify-center bg-black/55 px-4 backdrop-blur-sm">
                    <div className="w-full max-w-sm rounded-lg border border-white/25 bg-white p-5 text-slate-900 shadow-2xl">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <span className="inline-flex size-10 items-center justify-center rounded-lg bg-slate-900 text-white">
                            <Languages className="size-5" aria-hidden />
                          </span>
                          <div>
                            <h2 className="text-base font-semibold leading-6">
                              {voice.currentLanguage === 'ja'
                                ? 'スライド案内の言語'
                                : 'Slide Guide Language'}
                            </h2>
                            <p className="mt-1 text-sm leading-5 text-slate-600">
                              {voice.currentLanguage === 'ja'
                                ? '表示と音声の言語を選んでください。'
                                : 'Choose the language for slides and narration.'}
                            </p>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSlideLanguagePickerOpen(false)}
                          aria-label={voice.currentLanguage === 'ja' ? '閉じる' : 'Close'}
                          className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-600 transition-colors hover:bg-slate-50"
                        >
                          <X className="size-4" aria-hidden />
                        </button>
                      </div>
                      <div className="mt-5 grid grid-cols-2 gap-3">
                        <button
                          type="button"
                          data-testid="slide-language-ja"
                          onClick={() => startPresentation('ja')}
                          className="flex min-h-20 flex-col items-center justify-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-center transition-colors hover:border-slate-900 hover:bg-white"
                        >
                          <span className="text-lg font-semibold">日本語</span>
                          <span className="mt-1 text-xs text-slate-500">Japanese</span>
                        </button>
                        <button
                          type="button"
                          data-testid="slide-language-en"
                          onClick={() => startPresentation('en')}
                          className="flex min-h-20 flex-col items-center justify-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-center transition-colors hover:border-slate-900 hover:bg-white"
                        >
                          <span className="text-lg font-semibold">English</span>
                          <span className="mt-1 text-xs text-slate-500">英語</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}

                {showSlideMode ? (
                  <div
                    className="pointer-events-none absolute inset-0 z-50 flex h-full w-full flex-col"
                    style={screenPadding}
                  >
                    <div
                      className="pointer-events-auto relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl bg-white/95 shadow-2xl transition-all duration-300 ease-out sm:rounded-[28px]"
                      onPointerDownCapture={bumpUserActivity}
                    >
                      <button
                        type="button"
                        onClick={handleCloseSlides}
                        aria-label={labels.closeSlides}
                        className="absolute right-2 top-2 z-30 inline-flex size-9 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105 sm:right-3 sm:top-3 sm:size-10"
                      >
                        <X className="size-4 sm:size-5" />
                      </button>
                      <ReceptionPdfGuide
                        language={presentationLanguage}
                        rotateLandscapeHint={labels.slideRotateHint}
                        autoStartKey={presentationAutoStartKey}
                        className="min-h-0 flex-1"
                        sessionId={voice.sessionId}
                        onVisemeControl={setVisemeFunction}
                        onExpressionControl={setExpressionFunction}
                        volume={Math.round(voice.volume * 100)}
                        onPresentationComplete={() => {
                          if (kioskPhaseRef.current === 'slides') {
                            scheduleReturnToIdle();
                          }
                        }}
                      />
                    </div>
                  </div>
                ) : null}
              </main>
            </>
          );
        }}
      </VoiceInterface>
    </>
  );
}

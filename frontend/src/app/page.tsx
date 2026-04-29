'use client';

import { markAudioUserInteraction } from '@/lib/audio/audio-user-interaction-gate';
import { startSensorPolling, stopSensorPolling } from '@/lib/api/device-webhook';
import { getStageBackgroundStyle } from '@/lib/get-stage-background-style';
import { overlayLabels } from '@/lib/kiosk-labels';
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
import { Settings, X } from 'lucide-react';
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
import MarpViewer from './components/MarpViewer';
import ReceptionPdfGuide from './components/ReceptionPdfGuide';
import ClockBadge from './components/ClockBadge';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './components/SettingsPanel';
import VoiceInterface, {
  type VoiceInterfaceMetadata,
} from './components/VoiceInterface';
import type { OcrResponse } from '@/lib/api/ocr-api';
import { startReception } from '@/lib/reception-api';
import { cancelSttWarmup, sendSttWarmup } from '@/lib/stt-warmup';

const kioskReceptionSlidesUsePdf =
  process.env.NEXT_PUBLIC_RECEPTION_SLIDE_RENDERER !== 'marp';

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
      clearReturnToIdleTimer();
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

  const handleCloseSlides = useCallback(() => {
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
        autoResumeListeningAfterAssistant={
          micInputMode === 'push_to_talk' ? false : kioskVoiceLocked
        }
        onVisemeControl={setVisemeFunction}
        showDefaultUI={false}
        onMetadataChange={setLatestMetadata}
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
            markAudioUserInteraction();
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
            paddingTop: 'max(1.5rem, env(safe-area-inset-top))',
            paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))',
            paddingLeft: 'max(1.5rem, env(safe-area-inset-left))',
            paddingRight: 'max(1.5rem, env(safe-area-inset-right))',
          } satisfies CSSProperties;


          const characterCameraOffset = { x: 0, y: 0, z: 0 };
          const characterModelOffset = { x: 0, y: 0, z: 0 };
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
                        on_open_slides={() => startPresentation(voice.currentLanguage)}
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
                    onStartPresentation={() => startPresentation(voice.currentLanguage)}
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

                {showSlideMode ? (
                  kioskReceptionSlidesUsePdf ? (
                    <div
                      className="pointer-events-none absolute inset-0 z-30 flex h-full w-full flex-col"
                      style={screenPadding}
                    >
                      <div
                        className="pointer-events-auto relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-[32px] bg-white/95 shadow-2xl transition-all duration-300 ease-out"
                        onPointerDownCapture={bumpUserActivity}
                      >
                        <button
                          type="button"
                          onClick={handleCloseSlides}
                          aria-label={labels.closeSlides}
                          className="absolute right-3 top-3 z-20 inline-flex size-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105"
                        >
                          <X className="size-5" />
                        </button>
                        <ReceptionPdfGuide
                          language={voice.currentLanguage}
                          rotateLandscapeHint={labels.slideRotateHint}
                          autoStartKey={presentationAutoStartKey}
                          className="min-h-0 flex-1 pt-11"
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
                  ) : (
                    <div
                      className="pointer-events-none absolute inset-y-0 right-0 z-30 flex w-full justify-end"
                      style={screenPadding}
                    >
                      <div
                        className="pointer-events-auto flex h-full w-full max-w-6xl transform-gpu rounded-[32px] bg-white/95 shadow-2xl transition-all duration-300 ease-out"
                        onPointerDownCapture={bumpUserActivity}
                      >
                        <div className="relative flex h-full w-full flex-col overflow-hidden rounded-[32px]">
                          <button
                            type="button"
                            onClick={handleCloseSlides}
                            aria-label={labels.closeSlides}
                            className="absolute right-4 top-4 z-10 inline-flex size-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg transition-transform duration-200 ease-out hover:scale-105"
                          >
                            <X className="size-5" />
                          </button>
                          <div className="h-full w-full pt-4">
                            <MarpViewer
                              language={voice.currentLanguage}
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
                      </div>
                    </div>
                  )
                ) : null}
              </main>
            </>
          );
        }}
      </VoiceInterface>
    </>
  );
}

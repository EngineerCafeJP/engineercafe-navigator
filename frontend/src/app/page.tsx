'use client';

import { markAudioUserInteraction } from '@/lib/audio/audio-user-interaction-gate';
import { overlayLabels } from '@/lib/kiosk-labels';
import {
  KIOSK_IDLE_MS,
  type KioskMicMode,
  type KioskPhase,
  type KioskTriggerMode,
  readKioskMicMode,
  readKioskTriggerMode,
  writeKioskMicMode,
  writeKioskTriggerMode,
} from '@/lib/kiosk-constants';
import ReactMarkdown from 'react-markdown';

import { cn } from '@/lib/cn';
import {
  Camera,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Presentation,
  SendHorizontal,
  Settings,
  Sparkles,
  TextQuote,
  Volume2,
  X,
  XCircle,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type MutableRefObject,
  type PointerEvent as ReactPointerEvent,
  type SetStateAction,
} from 'react';
import type { CharacterAnimationData } from './utils/character-animation-utils';
import type { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import SettingsPanel, {
  type SettingsPanelPropsFromSource,
} from './components/SettingsPanel';
import MarpViewer from './components/MarpViewer';
import InitialSettingsModal from './components/InitialSettingsModal';
import VoiceInterface, {
  type VoiceInterfaceMetadata,
  type VoiceSessionState,
} from './components/VoiceInterface';
import { OcrCameraView } from '@/components/reception/OcrCameraView';
import { ReceptionPanel } from '@/components/reception/ReceptionPanel';
import type { OcrResponse } from '@/lib/api/ocr-api';

const buttonCopy: Record<
  VoiceSessionState,
  'idleAction' | 'listeningAction' | 'processingAction' | 'speakingAction'
> = {
  idle: 'idleAction',
  listening: 'listeningAction',
  processing: 'processingAction',
  speaking: 'speakingAction',
};

type ConversationHistoryItem = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

function KioskVoiceStatusStack({
  enabled,
  labels,
  transcript,
  response,
  error,
  ocrStatus,
  isLoading,
  loadingMessage,
  sessionState,
}: {
  enabled: boolean;
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'];
  transcript: string;
  response: string;
  error: string | null;
  ocrStatus: {
    kind: 'member_card' | 'handwriting' | 'error';
    text: string;
    visibleUntil: number;
  } | null;
  isLoading: boolean;
  loadingMessage: string;
  sessionState: VoiceSessionState;
}) {
  const [transcriptVisibleUntil, setTranscriptVisibleUntil] = useState<number>(0);
  const [responseVisibleUntil, setResponseVisibleUntil] = useState<number>(0);
  const [errorVisibleUntil, setErrorVisibleUntil] = useState<number>(0);
  const [now, setNow] = useState<number>(Date.now());
  const previousSessionStateRef = useRef<VoiceSessionState>(sessionState);

  useEffect(() => {
    if (!enabled) {
      setTranscriptVisibleUntil(0);
      setResponseVisibleUntil(0);
      setErrorVisibleUntil(0);
      return;
    }
    if (transcript.length > 0) {
      setTranscriptVisibleUntil(Date.now() + 5000);
    }
  }, [enabled, transcript]);

  useEffect(() => {
    if (!enabled) {
      previousSessionStateRef.current = sessionState;
      return;
    }

    if (previousSessionStateRef.current === 'speaking' && sessionState === 'idle' && response.length > 0) {
      setResponseVisibleUntil(Date.now() + 5000);
    }
    previousSessionStateRef.current = sessionState;
  }, [enabled, response.length, sessionState]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    if (error) {
      setErrorVisibleUntil(Date.now() + 5000);
    }
    if (error && response.length > 0) {
      setResponseVisibleUntil(Date.now() + 5000);
    }
  }, [enabled, error, response.length]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timers: number[] = [];
    if (transcriptVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), transcriptVisibleUntil - now));
    }
    if (responseVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), responseVisibleUntil - now));
    }
    if (errorVisibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), errorVisibleUntil - now));
    }
    if (ocrStatus && ocrStatus.visibleUntil > now) {
      timers.push(window.setTimeout(() => setNow(Date.now()), ocrStatus.visibleUntil - now));
    }
    return () => {
      timers.forEach((timerId) => window.clearTimeout(timerId));
    };
  }, [enabled, errorVisibleUntil, now, ocrStatus, responseVisibleUntil, transcriptVisibleUntil]);

  if (!enabled) {
    return null;
  }

  const isSttLoading =
    isLoading &&
    (loadingMessage === '音声を文字にしています...' ||
      loadingMessage === 'Transcribing your speech...');
  const isTtsSynthesizing =
    isLoading && response.length > 0 && sessionState !== 'speaking';
  const isErrorVisible = Boolean(error) && errorVisibleUntil > now;
  const isOcrStatusVisible = Boolean(ocrStatus && ocrStatus.visibleUntil > now);
  const isResponseVisible =
    response.length > 0 &&
    (sessionState === 'speaking' || responseVisibleUntil > now);
  const isTranscriptVisible =
    transcript.length > 0 && !isSttLoading && transcriptVisibleUntil > now;

  if (!isSttLoading && !isTtsSynthesizing && !isTranscriptVisible && !isResponseVisible && !isErrorVisible && !isOcrStatusVisible) {
    return null;
  }

  return (
    <div className="w-full space-y-2">
      {isOcrStatusVisible && ocrStatus ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          {ocrStatus.kind === 'error' ? (
            <XCircle className="size-4 shrink-0 text-rose-300" />
          ) : ocrStatus.kind === 'handwriting' ? (
            <MessageSquare className="size-4 shrink-0" />
          ) : (
            <Camera className="size-4 shrink-0" />
          )}
          <span>{ocrStatus.text}</span>
        </div>
      ) : null}
      {isErrorVisible ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-rose-300/45 bg-rose-700/35 px-4 py-2 text-sm font-medium text-rose-50 shadow-sm backdrop-blur-sm">
          <XCircle className="size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
      {isSttLoading ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span>{labels.sttReading}</span>
        </div>
      ) : null}
      {isTranscriptVisible ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <TextQuote className="size-4 shrink-0" />
          <span>
            {labels.transcriptLabel}: {transcript}
          </span>
        </div>
      ) : null}
      {isTtsSynthesizing ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <Loader2 className="size-4 shrink-0 animate-spin" />
          <span>{labels.ttsSynthesizing}</span>
        </div>
      ) : null}
      {isResponseVisible ? (
        <div className="flex w-full items-center gap-2 rounded-xl border border-white/30 bg-black/35 px-4 py-2 text-sm font-medium text-white/95 shadow-sm backdrop-blur-sm">
          <Volume2 className="size-4 shrink-0" />
          <span>
            {labels.responseLabel}: {response}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function ConversationHistoryEffects({
  transcript,
  response,
  lastTranscriptRef,
  lastResponseRef,
  setConversationHistory,
}: {
  transcript: string;
  response: string;
  lastTranscriptRef: MutableRefObject<string>;
  lastResponseRef: MutableRefObject<string>;
  setConversationHistory: Dispatch<SetStateAction<ConversationHistoryItem[]>>;
}) {
  useEffect(() => {
    if (transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'user',
          text: transcript,
        },
      ]);
    }
  }, [lastTranscriptRef, setConversationHistory, transcript]);

  useEffect(() => {
    if (response && response !== lastResponseRef.current) {
      lastResponseRef.current = response;
      setConversationHistory((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'assistant',
          text: response,
        },
      ]);
    }
  }, [lastResponseRef, response, setConversationHistory]);

  return null;
}

const getStageBackgroundStyle = (background: BackgroundOption): CSSProperties => {
  if (background.type === 'image') {
    return {
      backgroundImage: `url(${background.value})`,
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
      backgroundSize: 'cover',
    };
  }

  if (background.type === 'gradient') {
    return { background: background.value };
  }

  return background.value ? { backgroundColor: background.value } : {};
};

export default function Home() {
  const [kioskPhase, setKioskPhase] = useState<KioskPhase>('notice');
  const kioskPhaseRef = useRef<KioskPhase>('notice');
  const [kioskVoiceLocked, setKioskVoiceLocked] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>('ja');
  const [triggerMode, setTriggerMode] = useState<KioskTriggerMode>(() => readKioskTriggerMode());
  const [micInputMode, setMicInputMode] = useState<KioskMicMode>(() => readKioskMicMode());
  const [ocrMode, setOcrMode] = useState<'member_card' | 'handwriting'>('member_card');
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
  const [setVisemeFunction, setSetVisemeFunction] = useState<((viseme: string, intensity: number) => void) | null>(null);
  const [setExpressionFunction, setSetExpressionFunction] = useState<((expression: string, weight: number) => void) | null>(null);
  const [textDraft, setTextDraft] = useState('');
  const [showTextInput, setShowTextInput] = useState(false);
  const [, setLatestMetadata] = useState<VoiceInterfaceMetadata | null>(null);
  const [conversationHistory, setConversationHistory] = useState<ConversationHistoryItem[]>([]);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const settingsPanelPropsRef = useRef<SettingsPanelPropsFromSource | null>(null);
  const [settingsPanelProps, setSettingsPanelProps] =
    useState<SettingsPanelPropsFromSource | null>(null);
  const playKeyframeAnimationRef = useRef<((data: CharacterAnimationData) => void) | null>(null);
  const lastVrmControlPlayedRef = useRef<unknown>(null);
  /** Set when vrm_control playback runs before keyframe control ref is ready; flushed in onKeyframeAnimationControl. */
  const pendingVrmPlaybackRef = useRef<CharacterAnimationData | null>(null);
  const lastTranscriptRef = useRef<string>('');
  const lastResponseRef = useRef<string>('');
  const returnToIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kioskVoiceCleanupRef = useRef<(() => void) | null>(null);

  const showAvatarControls = process.env.NEXT_PUBLIC_SHOW_AVATAR_SETTINGS === 'true';

  useEffect(() => {
    kioskPhaseRef.current = kioskPhase;
  }, [kioskPhase]);

  const clearReturnToIdleTimer = useCallback(() => {
    if (returnToIdleTimerRef.current !== null) {
      clearTimeout(returnToIdleTimerRef.current);
      returnToIdleTimerRef.current = null;
    }
  }, []);

  const scheduleReturnToIdle = useCallback(() => {
    clearReturnToIdleTimer();
    returnToIdleTimerRef.current = setTimeout(() => {
      returnToIdleTimerRef.current = null;
      const phase = kioskPhaseRef.current;
      if (phase === 'voice' || phase === 'welcome') {
        kioskVoiceCleanupRef.current?.();
      }
      setKioskPhase('idle');
    }, KIOSK_IDLE_MS);
  }, [clearReturnToIdleTimer]);

  const bumpUserActivity = useCallback(() => {
    if (kioskPhaseRef.current === 'notice' || kioskPhaseRef.current === 'idle') {
      return;
    }
    clearReturnToIdleTimer();
  }, [clearReturnToIdleTimer]);

  useEffect(() => {
    return () => {
      clearReturnToIdleTimer();
    };
  }, [clearReturnToIdleTimer]);

  useEffect(() => {
    if (kioskPhase === 'ocr') {
      scheduleReturnToIdle();
    }
  }, [kioskPhase, scheduleReturnToIdle]);

  useEffect(() => {
    if (kioskPhase !== 'voice' && kioskVoiceLocked) {
      setKioskVoiceLocked(false);
    }
  }, [kioskPhase, kioskVoiceLocked]);

  const handleSettingsPanelPropsChange = useCallback(
    (props: SettingsPanelPropsFromSource) => {
      settingsPanelPropsRef.current = props;
      // Avoid re-rendering the whole page when settings panel is closed.
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

  const startPresentation = useCallback((language: 'ja' | 'en') => {
    setCurrentLanguage(language);
    setKioskPhase('slides');

    window.setTimeout(() => {
      window.dispatchEvent(
        new CustomEvent('autoStartPresentation', {
          detail: { autoPlay: true, language },
        }),
      );
    }, 150);
  }, []);

  const handleCloseSlides = useCallback(() => {
    clearReturnToIdleTimer();
    setKioskPhase('idle');
  }, [clearReturnToIdleTimer]);

  return (
    <>
      <InitialSettingsModal
        language={currentLanguage}
        open={kioskPhase === 'notice'}
        onClose={() => setKioskPhase('idle')}
        onPreferencesSaved={(prefs) => {
          setCurrentLanguage(prefs.language);
          setTriggerMode(prefs.triggerMode);
          setMicInputMode(prefs.micMode);
        }}
      />
      <VoiceInterface
      language={currentLanguage}
      onLanguageChange={setCurrentLanguage}
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
        kioskVoiceCleanupRef.current = () => {
          voice.cancelSession();
          voice.clearConversation();
        };
        const labels = overlayLabels[voice.currentLanguage];
        const receptionTriggerType =
          triggerMode === 'device' ? 'sensor_trigger' : 'button_press';
        const showSlideMode = kioskPhase === 'slides';
        const stageBackgroundStyle = getStageBackgroundStyle(characterBackground);
        const isListening = voice.sessionState === 'listening';
        const isSpeaking = voice.sessionState === 'speaking';
        const visualState: VoiceSessionState =
          voice.sessionState === 'speaking'
            ? 'speaking'
            : voice.sessionState === 'listening'
              ? 'listening'
              : voice.sessionState === 'processing' || voice.isLoading
                ? 'processing'
                : 'idle';
        const isProcessing = visualState === 'processing';
        const showConversationReset =
          Boolean(voice.transcript) || Boolean(voice.response) || Boolean(voice.metadata);
        const canCancelTurn = voice.sessionState !== 'idle' || voice.isLoading;
        const waveformBars = (
          isListening || isSpeaking ? voice.waveformBars : [0.2, 0.28, 0.18, 0.26, 0.2]
        ).map((value) => Math.max(value, 0.16));
        const bubbleBody =
          voice.response || (voice.isLoading && voice.loadingMessage) || labels.defaultPrompt;
        const micButtonLabel = labels[buttonCopy[visualState]];
        const isInputDisabled = isListening || isProcessing;

        const screenPadding = {
          paddingTop: 'max(1.5rem, env(safe-area-inset-top))',
          paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))',
          paddingLeft: 'max(1.5rem, env(safe-area-inset-left))',
          paddingRight: 'max(1.5rem, env(safe-area-inset-right))',
        } satisfies CSSProperties;

        const characterCameraOffset = showSlideMode
          ? { x: 0.2, y: 0, z: 0.0 }
          : { x: 0, y: 0, z: 0 };
        const characterModelOffset = showSlideMode
          ? { x: -0.7, y: 0, z: 0 }
          : { x: 0, y: 0, z: 0 };
        const characterRotationOffset = showSlideMode
          ? { x: 0, y: 0.35, z: 0 }
          : { x: 0, y: -0.2, z: 0 };

        const submitTextDraft = async () => {
          markAudioUserInteraction();
          const trimmed = textDraft.trim();
          if (!trimmed) {
            return;
          }

          await voice.sendMessage(trimmed);
          setTextDraft('');
        };

        const pushToTalk = micInputMode === 'push_to_talk';
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
          setKioskPhase('idle');

          if (result.mode === 'member_card') {
            const memberText =
              result.member_number !== null
                ? `${labels.ocrMemberResult}: ${result.member_number}`
                : labels.ocrReadFailed;
            setOcrStatusMessage('member_card', memberText);
            return;
          }

          const recognized = (result.recognized_text ?? '').trim();
          if (!recognized) {
            setOcrStatusMessage('error', labels.ocrReadFailed);
            return;
          }

          setOcrStatusMessage('handwriting', `${labels.ocrHandwritingResult}: ${recognized}`);
          void voice.sendMessage(recognized);
        };

        const handleMicPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk || isProcessing || isSpeaking) {
            return;
          }
          e.preventDefault();
          e.currentTarget.setPointerCapture(e.pointerId);
          markAudioUserInteraction();
          if (!isListening) {
            void voice.startListening();
          }
        };

        const handleMicPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk) {
            return;
          }
          e.preventDefault();
          if (e.currentTarget.hasPointerCapture(e.pointerId)) {
            e.currentTarget.releasePointerCapture(e.pointerId);
          }
          if (isListening) {
            voice.stopListening();
          }
        };

        const handleMicPointerCancel = (e: ReactPointerEvent<HTMLButtonElement>) => {
          if (!pushToTalk) {
            return;
          }
          if (e.currentTarget.hasPointerCapture(e.pointerId)) {
            e.currentTarget.releasePointerCapture(e.pointerId);
          }
          if (isListening) {
            voice.stopListening();
          }
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

              <div
                className="pointer-events-none absolute inset-0 z-30"
                aria-hidden={!showSettingsPanel}
              >
                <div
                  className="pointer-events-auto absolute"
                  style={{
                    top: screenPadding.paddingTop,
                    right: screenPadding.paddingRight,
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setShowSettingsPanel(true)}
                    aria-label={voice.currentLanguage === 'ja' ? '設定' : 'Settings'}
                    className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-white/15 bg-black/45 text-white shadow-lg backdrop-blur-md transition-transform duration-200 ease-out hover:scale-105"
                  >
                    <Settings className="size-5" />
                  </button>
                </div>
              </div>

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

              {(kioskPhase === 'idle' || kioskPhase === 'voice') && (
                <div
                  className="pointer-events-auto absolute inset-x-0 bottom-0 z-[25] flex justify-center pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-2"
                >
                  <div className="flex w-full max-w-5xl flex-col items-stretch justify-center gap-2 sm:gap-3">
                    {(() => {
                      const isVoiceCaptureActive = kioskPhase === 'voice' && kioskVoiceLocked;
                      const isPushToTalk = micInputMode === 'push_to_talk';
                      const handleKioskVoiceStart = () => {
                        markAudioUserInteraction();
                        clearReturnToIdleTimer();
                        setKioskPhase('voice');
                        setKioskVoiceLocked(true);
                        void voice.startListening();
                      };
                      const handleKioskVoiceStop = () => {
                        setKioskVoiceLocked(false);
                        voice.stopListening();
                      };

                      return (
                        <>
                    <KioskVoiceStatusStack
                      enabled={kioskPhase === 'voice' || kioskPhase === 'idle'}
                      labels={labels}
                      transcript={voice.transcript}
                      response={voice.response}
                      error={voice.error}
                      ocrStatus={ocrStatus}
                      isLoading={voice.isLoading}
                      loadingMessage={voice.loadingMessage}
                      sessionState={voice.sessionState}
                    />
                    <div className="flex w-full flex-row flex-wrap items-stretch justify-center gap-2 sm:gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        setKioskPhase('welcome');
                      }}
                      disabled={isVoiceCaptureActive}
                      className={cn(
                        'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                        isVoiceCaptureActive
                          ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                          : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
                      )}
                    >
                      <Sparkles className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskWelcome}
                      </span>
                    </button>
                    <button
                      type="button"
                      onPointerDown={(event) => {
                        if (!isPushToTalk) {
                          return;
                        }
                        event.preventDefault();
                        event.currentTarget.setPointerCapture(event.pointerId);
                        if (!isVoiceCaptureActive) {
                          handleKioskVoiceStart();
                        }
                      }}
                      onPointerUp={(event) => {
                        if (!isPushToTalk) {
                          return;
                        }
                        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                          event.currentTarget.releasePointerCapture(event.pointerId);
                        }
                        if (isVoiceCaptureActive) {
                          handleKioskVoiceStop();
                        }
                      }}
                      onPointerCancel={(event) => {
                        if (!isPushToTalk) {
                          return;
                        }
                        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                          event.currentTarget.releasePointerCapture(event.pointerId);
                        }
                        if (isVoiceCaptureActive) {
                          handleKioskVoiceStop();
                        }
                      }}
                      onClick={(event) => {
                        if (isPushToTalk) {
                          event.preventDefault();
                          return;
                        }
                        if (isVoiceCaptureActive) {
                          handleKioskVoiceStop();
                          return;
                        }
                        handleKioskVoiceStart();
                      }}
                      className={cn(
                        'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                        isVoiceCaptureActive
                          ? 'border border-emerald-300/70 bg-emerald-500/55 text-white shadow-lg'
                          : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
                      )}
                    >
                      <Mic className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskVoice}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        setKioskPhase('ocr');
                      }}
                      disabled={isVoiceCaptureActive}
                      className={cn(
                        'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                        isVoiceCaptureActive
                          ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                          : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
                      )}
                    >
                      <Camera className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskOcr}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        markAudioUserInteraction();
                        startPresentation(voice.currentLanguage);
                      }}
                      disabled={isVoiceCaptureActive}
                      className={cn(
                        'flex min-h-[72px] min-w-[min(100%,7rem)] flex-1 flex-col items-center justify-center gap-1 rounded-2xl px-3 py-3 shadow-md backdrop-blur-sm transition-transform sm:min-h-[80px] sm:flex-initial sm:px-5',
                        isVoiceCaptureActive
                          ? 'cursor-not-allowed border border-slate-500/40 bg-slate-600/40 text-slate-300'
                          : 'border border-white/35 bg-white/15 text-white hover:scale-[1.02]',
                      )}
                    >
                      <Presentation className="size-6 shrink-0 sm:size-7" aria-hidden />
                      <span className="text-center text-xs font-semibold leading-tight sm:text-sm">
                        {labels.kioskSlides}
                      </span>
                    </button>
                    </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              )}

              {kioskPhase === 'welcome' && (
                <div
                  className="absolute inset-0 z-40 overflow-y-auto bg-black/55 p-4"
                  onPointerDownCapture={bumpUserActivity}
                >
                  <div className="mx-auto max-w-3xl pb-24 pt-8">
                    <ReceptionPanel
                      sessionId={voice.sessionId}
                      language={voice.currentLanguage}
                      triggerType={receptionTriggerType}
                      autoEnterWelcome
                      onAssistantMessageAdded={() => {
                        if (kioskPhaseRef.current === 'welcome') {
                          scheduleReturnToIdle();
                        }
                      }}
                      onReceptionComplete={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('voice');
                      }}
                      className="border-white/20 bg-white/95 shadow-xl"
                    />
                    <div className="mt-6 flex justify-center">
                      <button
                        type="button"
                        onClick={() => {
                          clearReturnToIdleTimer();
                          setKioskPhase('idle');
                        }}
                        className="inline-flex min-h-11 items-center justify-center rounded-full border border-white/30 bg-black/40 px-6 py-3 text-sm font-medium text-white backdrop-blur-md transition-colors hover:bg-black/55"
                      >
                        {labels.kioskBackIdle}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {kioskPhase === 'ocr' && (
                <div
                  className="absolute inset-0 z-40 overflow-y-auto bg-black/60 p-4"
                  onPointerDownCapture={bumpUserActivity}
                >
                  <div className="mx-auto max-w-lg rounded-[28px] border border-white/15 bg-white/95 p-5 shadow-xl md:p-8">
                    <div className="mb-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setOcrMode('member_card')}
                        className={cn(
                          'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                          ocrMode === 'member_card'
                            ? 'bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-700',
                        )}
                      >
                        {labels.ocrModeMember}
                      </button>
                      <button
                        type="button"
                        onClick={() => setOcrMode('handwriting')}
                        className={cn(
                          'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                          ocrMode === 'handwriting'
                            ? 'bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-700',
                        )}
                      >
                        {labels.ocrModeHandwriting}
                      </button>
                    </div>
                    <OcrCameraView
                      key={ocrMode}
                      mode={ocrMode}
                      sessionId={voice.sessionId}
                      onSuccess={handleOcrSuccess}
                      onFallback={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('idle');
                        setOcrStatusMessage('error', labels.ocrReadFailed);
                      }}
                      onSkip={() => {
                        clearReturnToIdleTimer();
                        setKioskPhase('idle');
                      }}
                    />
                    <div className="mt-6 flex justify-center">
                      <button
                        type="button"
                        onClick={() => {
                          clearReturnToIdleTimer();
                          setKioskPhase('idle');
                        }}
                        className="inline-flex min-h-11 items-center justify-center rounded-full bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800"
                      >
                        {labels.kioskBackIdle}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {showSlideMode ? (
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
              ) : null}


            </main>
          </>
        );
      }}
    </VoiceInterface>
    </>
  );
}

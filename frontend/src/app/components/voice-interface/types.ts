import type { ReactNode } from 'react';
import type { VoiceCharacterState } from '../../hooks/useVoiceSessionController';
import type { WakeWordMatch } from '../../hooks/useWakeWord';
import type { CharacterAnimationData } from '../../utils/character-animation-utils';

export type VoiceSessionState = 'idle' | 'listening' | 'processing' | 'speaking';

/** Semantic loading stage for kiosk UI; avoids coupling to localized loadingMessage strings. */
export type VoiceLoadingPhase = 'mic' | 'stt' | 'llm' | 'tts' | null;
export type VoiceUiLockState = 'normal' | 'locked' | 'interruptible';

export interface VoiceInterfaceMetadata {
  clarification?: {
    clarification_type?: string;
    [key: string]: unknown;
  };
  clarification_options?: string[];
  requires_followup?: boolean;
  reception_type?: string;
  vrm_control?: CharacterAnimationData | null;
  [key: string]: unknown;
}

export interface VoiceInterfaceRenderProps {
  sessionId: string;
  sessionState: VoiceSessionState;
  characterState: VoiceCharacterState;
  transcript: string;
  response: string;
  metadata: VoiceInterfaceMetadata | null;
  error: string | null;
  isLoading: boolean;
  loadingMessage: string;
  loadingPhase: VoiceLoadingPhase;
  uiLockState: VoiceUiLockState;
  currentLanguage: 'ja' | 'en';
  volume: number;
  isMuted: boolean;
  waveformBars: number[];
  wakeWord: {
    isSupported: boolean;
    isListening: boolean;
    error: string | null;
    lastMatch: WakeWordMatch | null;
  };
  startListening: () => Promise<boolean>;
  stopListening: () => void;
  cancelSession: () => void;
  clearConversation: () => void;
  clearVisitState: () => void;
  unlockAudioPlayback: () => boolean;
  sendMessage: (message: string) => Promise<void>;
  /** Speak fixed text (e.g. reception greeting) without running QA. */
  speakPreparedText: (
    text: string,
    metadataForPlayback?: VoiceInterfaceMetadata | null,
  ) => Promise<void>;
  setVolume: (value: number) => void;
  setMuted: (value: boolean) => void;
  toggleLanguage: () => void;
}

export interface VoiceInterfaceProps {
  onLanguageChange?: (language: 'ja' | 'en') => void;
  layout?: 'vertical' | 'horizontal';
  language?: 'ja' | 'en';
  /** When false, idle wake-word listening is off (no mic via Web Speech API). Default true. */
  wakeWordEnabled?: boolean;
  /**
   * When false, after assistant TTS the session does not auto-return to listening (mic stays off until the user starts again).
   * Use for kiosk push-to-talk. Default true (continuous toggle conversations).
   */
  autoResumeListeningAfterAssistant?: boolean;
  autoGreeting?: boolean;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  children?: (props: VoiceInterfaceRenderProps) => ReactNode;
  showDefaultUI?: boolean;
  className?: string;
  onMetadataChange?: (metadata: VoiceInterfaceMetadata | null) => void;
  onAssistantPlaybackStart?: (payload: { metadata: VoiceInterfaceMetadata | null }) => void;
  /** Fired when assistant TTS finishes (session goes from speaking to idle). */
  onAssistantPlaybackEnd?: () => void;
  /** Optional VRM hook while parallel filler / QA runs after STT. */
  onVoiceTurnThinkingVisual?: () => void;
  /** Optional VRM hook when assistant audio is about to play (after filler). */
  onVoiceTurnAssistantSpeakingVisual?: () => void;
  /** Consumes SlideAgent responses so the kiosk can open the PDF guide instead of speaking slide text. */
  onSlideAgentResponse?: (payload: {
    answer: string;
    metadata: VoiceInterfaceMetadata | null;
  }) => void;
}

export type VoiceTimingTelemetry = {
  durationMs?: number;
  sttMs?: number;
  qaMs?: number;
  ttsMs?: number;
  playbackStartMs?: number;
  turnTotalMs?: number;
  requestMode?: string;
  usedProxyFallback?: boolean;
  status?: number;
  upstreamStatus?: Record<string, unknown> | null;
  from?: string;
  to?: string;
  characterState?: string;
  isConversationActive?: boolean;
  shouldListen?: boolean;
};

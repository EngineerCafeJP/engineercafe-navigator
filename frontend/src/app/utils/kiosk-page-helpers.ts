import { overlayLabels } from '@/lib/kiosk-labels';
import type { VoiceInterfaceRenderProps } from '../components/VoiceInterface';

export type WelcomeTriggerSource = 'screen' | 'device';

export function kioskVoiceModeBadgeLabel(
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

export function formatMemberNumberSuccess(
  labels: (typeof overlayLabels)['ja'] | (typeof overlayLabels)['en'],
  memberNumber: number,
): string {
  return labels.ocrMemberReadSuccess.replace('{memberNumber}', String(memberNumber));
}

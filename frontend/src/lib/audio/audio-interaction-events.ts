export const AUDIO_INTERACTION_REQUIRED_EVENT = 'engineer-cafe:audio-interaction-required';

export type AudioInteractionRequiredReason =
  | 'context-suspended'
  | 'context-interrupted'
  | 'playback-blocked'
  | 'decode-blocked';

export interface AudioInteractionRequiredEventDetail {
  reason: AudioInteractionRequiredReason;
  message?: string;
  audioContextState?: AudioContextState | 'interrupted' | null;
}

export type AudioInteractionRequiredListener = (
  detail: AudioInteractionRequiredEventDetail,
) => void;

export function dispatchAudioInteractionRequired(
  detail: AudioInteractionRequiredEventDetail,
): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(
    new CustomEvent<AudioInteractionRequiredEventDetail>(AUDIO_INTERACTION_REQUIRED_EVENT, {
      detail,
    }),
  );
}

export function addAudioInteractionRequiredListener(
  listener: AudioInteractionRequiredListener,
): () => void {
  if (typeof window === 'undefined') {
    return () => undefined;
  }

  const handler = (event: Event) => {
    listener((event as CustomEvent<AudioInteractionRequiredEventDetail>).detail);
  };

  window.addEventListener(AUDIO_INTERACTION_REQUIRED_EVENT, handler);
  return () => window.removeEventListener(AUDIO_INTERACTION_REQUIRED_EVENT, handler);
}

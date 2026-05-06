export type StaticNarrationAudioState = 'pending' | 'ready' | 'failed';

export function canUseStaticNarrationAudio(
  state: StaticNarrationAudioState | undefined,
): boolean {
  return state === 'ready';
}

export function isAudioInteractionRequired(error: unknown): boolean {
  const candidate = error as
    | { name?: unknown; message?: unknown; requiresUserInteraction?: unknown }
    | null
    | undefined;
  const name = typeof candidate?.name === 'string' ? candidate.name : '';
  const message = typeof candidate?.message === 'string' ? candidate.message : '';
  return (
    name === 'NotAllowedError' ||
    candidate?.requiresUserInteraction === true ||
    message.toLowerCase().includes('interaction')
  );
}

export function shouldFallbackToGeneratedNarration(error: unknown): boolean {
  return !isAudioInteractionRequired(error);
}

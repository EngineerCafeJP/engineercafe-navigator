export interface VoiceFillerPlaybackGate {
  canEnqueue: (audioResponse: unknown) => audioResponse is string;
  close: () => void;
}

/**
 * Keeps parallel filler audio from arriving after the real assistant response is ready.
 */
export function createVoiceFillerPlaybackGate(
  signal?: Pick<AbortSignal, 'aborted'>,
): VoiceFillerPlaybackGate {
  let accepting = true;

  return {
    canEnqueue(audioResponse: unknown): audioResponse is string {
      return (
        accepting &&
        signal?.aborted !== true &&
        typeof audioResponse === 'string' &&
        audioResponse.length > 0
      );
    },
    close() {
      accepting = false;
    },
  };
}

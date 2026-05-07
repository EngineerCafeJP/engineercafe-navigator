export type VoiceResponseLanguage = 'ja' | 'en';

function normalizeVoiceLanguage(value: unknown): VoiceResponseLanguage | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim().toLowerCase().split('-', 1)[0];
  return normalized === 'ja' || normalized === 'en' ? normalized : null;
}

export function resolveVoiceResponseLanguage(
  metadata: Record<string, unknown> | null | undefined,
  fallback: VoiceResponseLanguage,
): VoiceResponseLanguage {
  return (
    normalizeVoiceLanguage(metadata?.response_language) ??
    normalizeVoiceLanguage(metadata?.language) ??
    normalizeVoiceLanguage(metadata?.detectedLanguage) ??
    fallback
  );
}

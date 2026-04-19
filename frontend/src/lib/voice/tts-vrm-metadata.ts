import type { CharacterAnimationData } from '@/app/utils/character-animation-utils';

export type PlaybackMetadata = Record<string, unknown> & {
  vrm_control?: CharacterAnimationData | null;
};

export function mergePlaybackMetadataWithTtsVrmControl(
  base: PlaybackMetadata | null,
  ttsPayload: Record<string, unknown>,
): PlaybackMetadata | null {
  const ttsVrm = ttsPayload.vrmControl ?? ttsPayload.vrm_control;
  if (ttsVrm && typeof ttsVrm === 'object' && !Array.isArray(ttsVrm)) {
    return { ...(base ?? {}), vrm_control: ttsVrm as CharacterAnimationData };
  }

  if (!base?.vrm_control) {
    return base;
  }

  const { vrm_control: _staleVrmControl, ...rest } = base;
  return Object.keys(rest).length > 0 ? rest : null;
}

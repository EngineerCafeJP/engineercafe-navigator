import type { VRM } from '@pixiv/three-vrm';

type JsonRecord = Record<string, unknown>;

export const VISEME_NAMES = ['aa', 'ih', 'ou', 'ee', 'oh'] as const;
export const MIN_LIP_SYNC_UI_FACTOR = 0.2;
export const VISEME_SMOOTHING_ALPHA = 0.35;

export const getSessionPoseOffsets = (sessionState: 'idle' | 'listening' | 'processing' | 'speaking') => {
  switch (sessionState) {
    case 'listening':
      return {
        position: { x: 0, y: 0, z: 0.08 },
        rotation: { x: -0.08, y: 0, z: 0 },
        expression: 'happy',
        animation: 'idle',
      };
    case 'processing':
      return {
        position: { x: 0.02, y: 0, z: 0.04 },
        rotation: { x: -0.03, y: 0.08, z: 0.03 },
        expression: 'thinking',
        animation: 'thinking',
      };
    case 'speaking':
      return {
        position: { x: 0.03, y: 0, z: 0.05 },
        rotation: { x: -0.04, y: -0.04, z: 0 },
        expression: 'happy',
        animation: 'idle',
      };
    default:
      return {
        position: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0 },
        expression: 'neutral',
        animation: 'idle',
      };
  }
};

export const getRootScenePosition = (
  modelPositionOffset: { x: number; y: number; z: number },
  sessionState: 'idle' | 'listening' | 'processing' | 'speaking',
) => {
  const sessionPose = getSessionPoseOffsets(sessionState);

  return {
    x: modelPositionOffset.x + sessionPose.position.x,
    y: modelPositionOffset.y + sessionPose.position.y,
    z: modelPositionOffset.z + sessionPose.position.z,
  };
};

const asRecord = (value: unknown): JsonRecord | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as JsonRecord;
};

export const getVrmSpecVersion = (gltf: { parser?: { json?: { extensions?: JsonRecord } } }, vrm?: VRM | null): string | null => {
  const extensions = gltf.parser?.json?.extensions;
  const vrm0Extension = asRecord(extensions?.VRM);
  if (typeof vrm0Extension?.specVersion === 'string') {
    return vrm0Extension.specVersion;
  }

  const vrm1Extension = asRecord(extensions?.VRMC_vrm);
  if (typeof vrm1Extension?.specVersion === 'string') {
    return vrm1Extension.specVersion;
  }

  const vrmMeta = asRecord(asRecord(vrm)?.meta);
  if (typeof vrmMeta?.metaVersion === 'string') {
    return vrmMeta.metaVersion;
  }

  return null;
};

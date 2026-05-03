import { VRM } from '@pixiv/three-vrm';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

import { EmotionMapping } from '@/lib/emotion-mapping';

/** Same default as CharacterAvatar (1m ahead, 1m up) for VRMLookAt when loading VRMA. */
const FALLBACK_LOOK_AT_POSITION = new THREE.Vector3(0, 1, 1);

/**
 * Maps a supported animation key to its public `.vrma` URL (same rule as
 * {@code CharacterAvatar} {@code /animations/${animation}.vrma}).
 */
export function vrmaUrlForAnimationName(animationName: string): string {
  return `/animations/${animationName}.vrma`;
}

/**
 * Standby / default character VRMA: tied to {@link EmotionMapping.DEFAULT_ANIMATION}
 * (`idle`), not file-name heuristics.
 */
export const DEFAULT_IDLE_VRMA_URL = vrmaUrlForAnimationName(EmotionMapping.DEFAULT_ANIMATION);

/** Normalizes request URLs for same-asset comparison (query stripped, path-only for absolute URLs). */
export function normalizeVrmaAssetPath(animationUrl: string): string {
  const raw = animationUrl.split('?')[0] ?? animationUrl;
  if (/^https?:\/\//i.test(raw)) {
    try {
      return new URL(raw).pathname;
    } catch {
      return raw;
    }
  }
  const path = raw.startsWith('/') ? raw : `/${raw}`;
  return path.replace(/\/{2,}/g, '/');
}

/**
 * True when {@code animationUrl} resolves to the same asset as {@link DEFAULT_IDLE_VRMA_URL}
 * (standby animation from {@link EmotionMapping}).
 */
export function isDefaultIdleVrmaRequest(animationUrl: string): boolean {
  return normalizeVrmaAssetPath(animationUrl) === normalizeVrmaAssetPath(DEFAULT_IDLE_VRMA_URL);
}

function ensureVrmLookAtTarget(vrm: VRM): void {
  if (!vrm.lookAt) {
    return;
  }
  if (!vrm.lookAt.target) {
    const fallback = new THREE.Object3D();
    fallback.position.copy(FALLBACK_LOOK_AT_POSITION);
    vrm.lookAt.target = fallback;
  }
}

/**
 * Loads a .vrma (or gltf animation) and returns a Three.js {@link THREE.AnimationClip}
 * using the same rules as {@code CharacterAvatar.loadVRMAnimation}.
 */
export async function loadVRMAAnimationClipFromUrl(
  animationUrl: string,
  vrm: VRM,
): Promise<{ clip: THREE.AnimationClip | null; duration: number }> {
  const loader = new GLTFLoader();
  loader.crossOrigin = 'anonymous';
  loader.register((parser) => new VRMAnimationLoaderPlugin(parser));

  const gltf = await loader.loadAsync(animationUrl);
  const vrmAnimation = gltf.userData.vrmAnimations?.[0] || gltf.userData.vrmAnimation;

  let clip: THREE.AnimationClip | null = null;

  if (vrmAnimation) {
    if (vrm.lookAt) {
      ensureVrmLookAtTarget(vrm);
      clip = createVRMAnimationClip(vrmAnimation, vrm as any);
    }
    if (!clip && gltf.animations?.length) {
      clip = gltf.animations[0];
    }
  } else if (gltf.animations?.length) {
    clip = gltf.animations[0];
  }

  return { clip, duration: clip?.duration ?? 0 };
}

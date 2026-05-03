import { VRM } from '@pixiv/three-vrm';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

/** Same default as CharacterAvatar (1m ahead, 1m up) for VRMLookAt when loading VRMA. */
const FALLBACK_LOOK_AT_POSITION = new THREE.Vector3(0, 1, 1);

export const DEFAULT_IDLE_VRMA_URL = '/animations/idle.vrma';

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

/** Whether {@code animationUrl} points at {@link DEFAULT_IDLE_VRMA_URL}-style idle VRMA. */
export function isIdleVrmaUrl(animationUrl: string): boolean {
  const pathOnly = animationUrl.split('?')[0] ?? animationUrl;
  return pathOnly.endsWith('/idle.vrma') || pathOnly.endsWith('idle.vrma');
}

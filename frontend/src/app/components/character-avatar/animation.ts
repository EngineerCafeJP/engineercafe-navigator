import { DEFAULT_IDLE_VRMA_URL, isDefaultIdleVrmaRequest, loadVRMAAnimationClipFromUrl } from '@/lib/vrm-animation-clip';
import { VRMUtils } from '@/lib/vrm-utils';
import type { VRM } from '@pixiv/three-vrm';
import type { MutableRefObject } from 'react';
import * as THREE from 'three';

interface LoadCharacterVrmAnimationArgs {
  animationUrl: string;
  vrm: VRM;
  loop?: boolean;
  mixerRef: MutableRefObject<THREE.AnimationMixer | null>;
  currentActionRef: MutableRefObject<THREE.AnimationAction | null>;
  currentRebasedClipRef: MutableRefObject<THREE.AnimationClip | null>;
  idleHipsBaselineRef: MutableRefObject<{ x: number; z: number } | null>;
  applyRootScenePosition: (vrm?: VRM | null) => void;
}

export const loadCharacterVrmAnimation = async ({
  animationUrl,
  vrm,
  loop = true,
  mixerRef,
  currentActionRef,
  currentRebasedClipRef,
  idleHipsBaselineRef,
  applyRootScenePosition,
}: LoadCharacterVrmAnimationArgs) => {
  try {
    const { clip: initialClip } = await loadVRMAAnimationClipFromUrl(animationUrl, vrm);
    if (!initialClip) {
      return { success: false, duration: 0 };
    }
    let clip = initialClip;

    if (isDefaultIdleVrmaRequest(animationUrl)) {
      const baseline = VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0);
      if (baseline) {
        idleHipsBaselineRef.current = baseline;
      }
    } else {
      let baseline = idleHipsBaselineRef.current;
      if (!baseline) {
        try {
          const idlePack = await loadVRMAAnimationClipFromUrl(DEFAULT_IDLE_VRMA_URL, vrm);
          if (idlePack.clip) {
            baseline = VRMUtils.sampleHipsPositionXZAtTime(idlePack.clip, vrm, 0);
            if (baseline) {
              idleHipsBaselineRef.current = baseline;
            }
          }
        } catch {
          baseline = null;
        }
      }
      const other = VRMUtils.sampleHipsPositionXZAtTime(clip, vrm, 0);
      if (baseline && other) {
        clip = VRMUtils.rebaseHipsHorizontalInClip(clip, vrm, baseline, other);
      }
    }

    if (!mixerRef.current) {
      mixerRef.current = new THREE.AnimationMixer(vrm.scene);
    }

    if (currentActionRef.current) {
      currentActionRef.current.stop();
    }
    if (currentRebasedClipRef.current && currentRebasedClipRef.current !== clip) {
      mixerRef.current.uncacheClip(currentRebasedClipRef.current);
      currentRebasedClipRef.current = null;
    }

    const action = mixerRef.current.clipAction(clip);
    if (loop) {
      action.setLoop(THREE.LoopRepeat, Infinity);
    } else {
      action.setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
    }
    action.play();
    currentActionRef.current = action;
    currentRebasedClipRef.current = clip !== initialClip ? clip : null;

    applyRootScenePosition(vrm);

    return { success: true, duration: clip.duration };
  } catch (error) {
    console.error('Error loading VRM animation:', error);
  }

  return { success: false, duration: 0 };
};

export const playRandomVrmAnimation = async (
  vrm: VRM,
  loadVRMAnimation: (animationUrl: string, vrm: VRM, loop?: boolean) => Promise<{ success: boolean; duration: number }>,
) => {
  // 実ファイル名の一覧を /api/animations (manifest.json) から動的取得する。
  // 以前は ['VRMA_03'..'VRMA_07'] をハードコードしていたが、存在しない
  // ファイル名のため 404 になりクリックアニメーションが機能しなかった (#948)。
  let animations: string[];
  try {
    const response = await fetch('/api/animations');
    const result = (await response.json()) as { animations?: string[] };
    animations = (result.animations ?? [])
      .map((name) => name.replace(/\.vrma$/i, ''))
      .filter((name) => name.length > 0);
  } catch (error) {
    console.error('Failed to fetch VRM animation list:', error);
    animations = [];
  }

  // idle は待機モーションなのでランダム対象から除外し、それ以外から選ぶ
  const candidates = animations.filter((name) => name !== 'idle');
  if (candidates.length === 0) {
    // フォールバック: 既知のクリック用アニメーション名
    candidates.push('bowing', 'greeting', 'looking', 'surprised', 'talking', 'thinking', 'thinking2');
  }

  // Select a random animation
  const randomIndex = Math.floor(Math.random() * candidates.length);
  const animName = candidates[randomIndex];
  const animUrl = `/animations/${animName}.vrma`;

  try {
    // Load animation without looping and get its duration
    const result = await loadVRMAnimation(animUrl, vrm, false);

    if (result.success) {
      // Wait for the animation to complete based on its actual duration
      const waitTime = (result.duration * 1000) + 100; // Add 100ms buffer
      await new Promise(resolve => setTimeout(resolve, waitTime));
    } else {
      // Fallback wait time if duration couldn't be determined
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  } catch (error) {
    console.error(`Failed to play animation ${animName}:`, error);
  }

  // Return to idle animation
  await loadVRMAnimation(DEFAULT_IDLE_VRMA_URL, vrm, true);
};

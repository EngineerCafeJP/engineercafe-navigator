import { getLipSyncFactorFromEmotions, VRMBlendShapeController, VRMUtils } from '@/lib/vrm-utils';
import type { VRM } from '@pixiv/three-vrm';
import type { MutableRefObject } from 'react';
import * as THREE from 'three';
import type { CharacterAnimationData } from '../../utils/character-animation-utils';
import {
  MIN_LIP_SYNC_UI_FACTOR,
  VISEME_NAMES,
  VISEME_SMOOTHING_ALPHA,
} from './utils';

export const createVisemeSetter = (
  blendShapeControllerRef: MutableRefObject<VRMBlendShapeController | null>,
  expressionWeightsAppliedRef: MutableRefObject<Record<string, number>>,
) => {
  return (viseme: string, intensity: number) => {
    if (blendShapeControllerRef.current) {
      const visemeMap: Record<string, string> = {
        'A': 'aa',
        'I': 'ih',
        'U': 'ou',
        'E': 'ee',
        'O': 'oh',
        'Closed': 'neutral',
      };
      const vrmExpression = visemeMap[viseme] || 'neutral';
      const factor = getLipSyncFactorFromEmotions(expressionWeightsAppliedRef.current);
      blendShapeControllerRef.current.setViseme(vrmExpression, intensity * factor);
    }
  };
};

export const createExpressionSetter = (
  charactersRef: MutableRefObject<VRM | null>,
  blendShapeControllerRef: MutableRefObject<VRMBlendShapeController | null>,
  expressionTimeoutRef: MutableRefObject<NodeJS.Timeout | null>,
  currentExpressionRef: MutableRefObject<{ expression: string; weight: number }>,
) => {
  return (expression: string, weight: number) => {
    // Clear existing timeout if any
    if (expressionTimeoutRef.current) {
      clearTimeout(expressionTimeoutRef.current);
      expressionTimeoutRef.current = null;
    }

    // Map expressions to available ones if VRM doesn't support them
    // Fallback to expressions that are guaranteed to exist in the VRM model
    const expressionFallbackMap: Record<string, string> = {
      'curious': 'neutral', // curious doesn't exist in VRM
      'surprised': 'happy', // surprised might not exist in some VRM models, use happy as fallback
    };

    const mappedExpression = expressionFallbackMap[expression] || expression;

    if (blendShapeControllerRef.current) {
      // Use the VRM expression manager to set expressions (use ref so setExpression works outside inner try scope)
      const expressionManager = charactersRef.current?.expressionManager;

      if (expressionManager) {
        // Log available expressions for debugging
        const availableExpressions = Object.keys(expressionManager.expressionMap);

        // Reset all expressions first if weight is significant
        if (weight > 0.1) {
          availableExpressions.forEach(name => {
            if (name !== expression) {
              expressionManager.setValue(name, 0);
            }
          });
        }

        const resetToNeutralLater = (name: string) => {
          if (name !== 'neutral' && weight > 0.1) {
            expressionTimeoutRef.current = setTimeout(() => {
              // Gradually transition back to neutral
              availableExpressions.forEach(availableName => {
                if (availableName !== 'neutral') {
                  expressionManager.setValue(availableName, 0);
                }
              });
              expressionManager.setValue('neutral', 1.0);
              currentExpressionRef.current = { expression: 'neutral', weight: 1.0 };
            }, 5000);
          }
        };

        // Set the target expression
        if (expressionManager.expressionMap[mappedExpression]) {
          expressionManager.setValue(mappedExpression, weight);
          currentExpressionRef.current = { expression: mappedExpression, weight };
          resetToNeutralLater(mappedExpression);
        } else {
          // Try to find a similar expression
          const similarExpression = availableExpressions.find(name =>
            name.toLowerCase().includes(mappedExpression.toLowerCase()) ||
            mappedExpression.toLowerCase().includes(name.toLowerCase())
          );

          if (similarExpression) {
            expressionManager.setValue(similarExpression, weight);
            currentExpressionRef.current = { expression: similarExpression, weight };
            resetToNeutralLater(similarExpression);
          } else {
            // Fallback to neutral expression which should always exist
            expressionManager.setValue('neutral', 1.0);
            currentExpressionRef.current = { expression: 'neutral', weight: 1.0 };
          }
        }
      } else {
        console.error('[CharacterAvatar] Expression manager not available');
      }
    } else {
      console.error('[CharacterAvatar] BlendShape controller not available');
    }
  };
};

export const createKeyframeAnimationPlayer = (
  charactersRef: MutableRefObject<VRM | null>,
  blendShapeControllerRef: MutableRefObject<VRMBlendShapeController | null>,
  keyframeAnimationTimeoutsRef: MutableRefObject<NodeJS.Timeout[]>,
  isPlayingSequence: MutableRefObject<boolean>,
  setExpressionWeightsRef: MutableRefObject<(weights: Record<string, number>) => void>,
) => {
  /** アニメーションを即時停止し、表情・口を neutral に戻す。
   * 音声再生が先に終わった場合に呼ばれる（キーフレーム duration は音声より長いため）。
   */
  const stopKeyframeAnimation = () => {
    keyframeAnimationTimeoutsRef.current.forEach((id) => clearTimeout(id));
    keyframeAnimationTimeoutsRef.current = [];
    isPlayingSequence.current = false;
    blendShapeControllerRef.current?.resetToNeutral();
  };

  const playKeyframeAnimation = (animation: CharacterAnimationData) => {
    const vrmRef = charactersRef.current;
    const blendShapeRef = blendShapeControllerRef.current;
    if (!vrmRef || !blendShapeRef) return;

    keyframeAnimationTimeoutsRef.current.forEach((id) => clearTimeout(id));
    keyframeAnimationTimeoutsRef.current = [];

    isPlayingSequence.current = true;

    animation.keyframes.forEach((keyframe) => {
      const timeoutId = setTimeout(() => {
        if (keyframe.bones) {
          Object.entries(keyframe.bones).forEach(([boneName, boneData]) => {
            const rot = boneData.rotation;
            const euler = new THREE.Euler(rot.x, rot.y, rot.z);
            VRMUtils.setHumanoidBoneRotation(vrmRef, boneName, euler, 0);
          });
        }
        if (keyframe.expressions && blendShapeControllerRef.current) {
          const factor = getLipSyncFactorFromEmotions(keyframe.expressions);
          const blended = { ...keyframe.expressions };
          VISEME_NAMES.forEach((name) => {
            const v = blended[name];
            if (typeof v === 'number') {
              blended[name] = v * factor;
            }
          });

          blendShapeControllerRef.current.setExpressions(blended);
          const current = blendShapeControllerRef.current.getCurrentExpressions();
          setExpressionWeightsRef.current(current);
        }
      }, keyframe.time);
      keyframeAnimationTimeoutsRef.current.push(timeoutId);
    });

    const endTimeout = setTimeout(() => {
      keyframeAnimationTimeoutsRef.current = [];
      isPlayingSequence.current = false;
      // アニメーション終了時に表情・口を neutral にリセットする。
      // リセットしないと最後のキーフレームの口形状が残り、
      // 「回答が終わった後もリップシンクが動き続ける」ように見える(#実機検証)。
      blendShapeControllerRef.current?.resetToNeutral();
    }, animation.duration + 100);
    keyframeAnimationTimeoutsRef.current.push(endTimeout);
  };

  return { play: playKeyframeAnimation, stop: stopKeyframeAnimation };
};

export const syncExpressionWeightsFromVrm = ({
  blendShapeController,
  expressionWeightsAppliedRef,
  lastManualExpressionUpdateMsRef,
  expressionWeightsUiRef,
  expressionWeightsDisplayRef,
  setExpressionWeightsRef,
}: {
  blendShapeController: VRMBlendShapeController | null;
  expressionWeightsAppliedRef: MutableRefObject<Record<string, number>>;
  lastManualExpressionUpdateMsRef: MutableRefObject<Record<string, number>>;
  expressionWeightsUiRef: MutableRefObject<Record<string, number>>;
  expressionWeightsDisplayRef: MutableRefObject<Record<string, number>>;
  setExpressionWeightsRef: MutableRefObject<(weights: Record<string, number>) => void>;
}) => {
  if (!blendShapeController) {
    return;
  }

  const current = blendShapeController.getCurrentExpressions();
  const last = expressionWeightsAppliedRef.current;
  const currentKeys = Object.keys(current);
  const lastKeys = Object.keys(last);
  const EPSILON = 0.0001;
  const MANUAL_HOLD_MS = 250;
  let changed = currentKeys.length !== lastKeys.length;
  if (!changed) {
    for (let i = 0; i < currentKeys.length; i++) {
      const name = currentKeys[i];
      const a = current[name] ?? 0;
      const b = last[name] ?? 0;
      if (Math.abs(a - b) > EPSILON) {
        changed = true;
        break;
      }
    }
  }
  if (!changed) {
    return;
  }

  const now = Date.now();
  const manual = lastManualExpressionUpdateMsRef.current;
  const ui = expressionWeightsUiRef.current;
  const factor = getLipSyncFactorFromEmotions(current);
  const display: Record<string, number> = { ...current };
  if (factor > 0.001) {
    const effectiveFactor = Math.max(factor, MIN_LIP_SYNC_UI_FACTOR);
    VISEME_NAMES.forEach((name) => {
      const v = display[name];
      if (typeof v === 'number') {
        display[name] = Math.max(0, Math.min(1, v / effectiveFactor));
      }
    });
  } else {
    VISEME_NAMES.forEach((name) => {
      if (typeof display[name] === 'number') {
        display[name] = 0;
      }
    });
  }

  const prevDisplay = expressionWeightsDisplayRef.current;
  VISEME_NAMES.forEach((name) => {
    const nextValue = display[name];
    const prevValue = prevDisplay[name];
    if (typeof nextValue === 'number' && typeof prevValue === 'number') {
      display[name] = prevValue + (nextValue - prevValue) * VISEME_SMOOTHING_ALPHA;
    }
  });

  for (const [name, ts] of Object.entries(manual)) {
    if (now - ts < MANUAL_HOLD_MS && typeof ui[name] === 'number') {
      display[name] = ui[name];
    }
  }

  setExpressionWeightsRef.current(display);
  expressionWeightsDisplayRef.current = { ...display };
  expressionWeightsAppliedRef.current = { ...current };
};

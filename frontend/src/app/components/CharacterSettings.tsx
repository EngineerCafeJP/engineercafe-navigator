'use client';

import React, { useEffect, useState } from 'react';
import { Play, User } from 'lucide-react';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import KeyframeSettings from './KeyframeSettings';

export interface ControlsState {
  expression: string;
  animation: string;
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number };
}

export interface VRMAnimationOption {
  value: string;
  label: string;
}

const DEFAULT_VRM_ANIMATION = '/animations/idle.vrma';

const VISEME_NAMES = ['aa', 'ih', 'ou', 'ee', 'oh'];

const VISEME_LABELS: Record<string, string> = {
  aa: 'A',
  ih: 'I',
  ou: 'U',
  ee: 'E',
  oh: 'O',
};

interface CharacterSettingsProps {
  state: ControlsState;
  vrmExpressionNames: string[];
  expressionWeights: Record<string, number>;
  onExpressionWeightChange: (name: string, weight: number) => void;
  vrmAnimationOptions?: VRMAnimationOption[];
  onPlayVRMAnimation?: (url: string, loop: boolean) => void;
  onPositionChange: (position: ControlsState['position']) => void;
  onRotationChange: (rotation: ControlsState['rotation']) => void;
  keyframe_json_input: string;
  on_keyframe_json_input_change: (value: string) => void;
  keyframe_json_error: string;
  on_keyframe_json_error: (message: string) => void;
  on_run_keyframe: (animation: CharacterAnimationData) => void;
}

export default function CharacterSettings({
  state,
  vrmExpressionNames,
  expressionWeights,
  onExpressionWeightChange,
  vrmAnimationOptions = [],
  onPlayVRMAnimation,
  onPositionChange,
  onRotationChange,
  keyframe_json_input,
  on_keyframe_json_input_change,
  keyframe_json_error,
  on_keyframe_json_error,
  on_run_keyframe,
}: CharacterSettingsProps) {
  const [selected_vrm_animation, set_selected_vrm_animation] = useState<string>(DEFAULT_VRM_ANIMATION);
  const [vrm_animation_loop, set_vrm_animation_loop] = useState(true);

  useEffect(() => {
    if (vrmAnimationOptions.length === 0) return;
    const in_list = vrmAnimationOptions.some((opt) => opt.value === selected_vrm_animation);
    if (!in_list) {
      const idle_option = vrmAnimationOptions.find((opt) => opt.value === DEFAULT_VRM_ANIMATION);
      set_selected_vrm_animation(idle_option ? idle_option.value : vrmAnimationOptions[0].value);
    }
  }, [vrmAnimationOptions, selected_vrm_animation]);

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <User className="w-4 h-4" />
        Character
      </h3>

      {vrmExpressionNames.length > 0 && (
        <>
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-700 mb-2">
              Expression (VRM)
            </label>
            <div className="space-y-2">
              {vrmExpressionNames
                .filter((name) => !VISEME_NAMES.includes(name))
                .map((name) => (
                  <div key={name} className="flex items-center gap-2">
                    <label className="text-xs text-gray-700 w-24 shrink-0 capitalize">
                      {name}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round((expressionWeights[name] ?? 0) * 100)}
                      onChange={(e) =>
                        onExpressionWeightChange(name, Number(e.target.value) / 100)
                      }
                      className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                    />
                    <span className="text-xs w-8 text-right text-gray-500">
                      {Math.round((expressionWeights[name] ?? 0) * 100)}%
                    </span>
                  </div>
                ))}
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-700 mb-2">
              Viseme (mouth shape / lip-sync)
            </label>
            <div className="space-y-2">
              {vrmExpressionNames
                .filter((name) => VISEME_NAMES.includes(name))
                .map((name) => (
                  <div key={name} className="flex items-center gap-2">
                    <label className="text-xs text-gray-700 w-24 shrink-0">
                      {VISEME_LABELS[name] ?? name} ({name})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round((expressionWeights[name] ?? 0) * 100)}
                      onChange={(e) =>
                        onExpressionWeightChange(name, Number(e.target.value) / 100)
                      }
                      className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                    />
                    <span className="text-xs w-8 text-right text-gray-500">
                      {Math.round((expressionWeights[name] ?? 0) * 100)}%
                    </span>
                  </div>
                ))}
            </div>
          </div>
        </>
      )}

      {vrmAnimationOptions.length > 0 && onPlayVRMAnimation && (
        <div className="mb-4">
          <label className="block text-xs font-medium text-gray-700 mb-2">
            VRM Animation (public/animations)
          </label>
          <div className="flex gap-2 items-center">
            <select
              value={selected_vrm_animation}
              onChange={(e) => set_selected_vrm_animation(e.target.value)}
              className="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs"
            >
              {vrmAnimationOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 shrink-0 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={vrm_animation_loop}
                onChange={(e) => set_vrm_animation_loop(e.target.checked)}
                className="rounded border-gray-300"
              />
              Loop
            </label>
            <button
              type="button"
              onClick={() =>
                selected_vrm_animation && onPlayVRMAnimation(selected_vrm_animation, vrm_animation_loop)
              }
              className="shrink-0 p-2 bg-blue-500 hover:bg-blue-600 text-white rounded-md transition-colors"
              title="Play VRM animation"
            >
              <Play className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">Position</label>
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <label className="text-xs w-4">X:</label>
            <input
              type="range"
              min="-2"
              max="2"
              step="0.1"
              value={state.position.x}
              onChange={(e) =>
                onPositionChange({ ...state.position, x: parseFloat(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-xs w-12">{state.position.x.toFixed(1)}</span>
          </div>
          <div className="flex items-center space-x-2">
            <label className="text-xs w-4">Y:</label>
            <input
              type="range"
              min="-2"
              max="2"
              step="0.1"
              value={state.position.y}
              onChange={(e) =>
                onPositionChange({ ...state.position, y: parseFloat(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-xs w-12">{state.position.y.toFixed(1)}</span>
          </div>
          <div className="flex items-center space-x-2">
            <label className="text-xs w-4">Z:</label>
            <input
              type="range"
              min="-2"
              max="2"
              step="0.1"
              value={state.position.z}
              onChange={(e) =>
                onPositionChange({ ...state.position, z: parseFloat(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-xs w-12">{state.position.z.toFixed(1)}</span>
          </div>
        </div>
      </div>

      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">Rotation</label>
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <label className="text-xs w-4">Y:</label>
            <input
              type="range"
              min="-3.14"
              max="3.14"
              step="0.1"
              value={state.rotation.y}
              onChange={(e) =>
                onRotationChange({ ...state.rotation, y: parseFloat(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-xs w-12">{state.rotation.y.toFixed(1)}</span>
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200">
        <KeyframeSettings
          jsonInput={keyframe_json_input}
          onJsonInputChange={on_keyframe_json_input_change}
          error={keyframe_json_error}
          onError={on_keyframe_json_error}
          onRunKeyframe={on_run_keyframe}
          embedded
        />
      </div>
    </div>
  );
}


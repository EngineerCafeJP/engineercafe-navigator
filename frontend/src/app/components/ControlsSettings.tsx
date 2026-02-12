'use client';

import React from 'react';
import { SlidersHorizontal } from 'lucide-react';

export interface ControlsState {
  expression: string;
  animation: string;
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number; z: number };
}

interface ControlsSettingsProps {
  state: ControlsState;
  availableExpressions: string[];
  availableAnimations: string[];
  onExpressionChange: (expression: string) => void;
  onAnimationChange: (animation: string) => void;
  onPositionChange: (position: ControlsState['position']) => void;
  onRotationChange: (rotation: ControlsState['rotation']) => void;
}

export default function ControlsSettings({
  state,
  availableExpressions,
  availableAnimations,
  onExpressionChange,
  onAnimationChange,
  onPositionChange,
  onRotationChange,
}: ControlsSettingsProps) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <SlidersHorizontal className="w-4 h-4" />
        Controls
      </h3>

      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">Expression</label>
        <select
          value={state.expression}
          onChange={(e) => onExpressionChange(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {availableExpressions.map((expression) => (
            <option key={expression} value={expression}>
              {expression.charAt(0).toUpperCase() + expression.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">Animation</label>
        <select
          value={state.animation}
          onChange={(e) => onAnimationChange(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {availableAnimations.map((animation) => (
            <option key={animation} value={animation}>
              {animation.charAt(0).toUpperCase() + animation.slice(1)}
            </option>
          ))}
        </select>
      </div>

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
    </div>
  );
}

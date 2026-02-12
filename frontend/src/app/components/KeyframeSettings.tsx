'use client';

import React from 'react';
import { Film } from 'lucide-react';
import type { CharacterAnimationData } from '../utils/character-animation-utils';
import {
  parse_character_animation_json,
  SAMPLE_JSON,
} from '../utils/character-animation-utils';

interface KeyframeSettingsProps {
  jsonInput: string;
  onJsonInputChange: (value: string) => void;
  error: string;
  onError: (message: string) => void;
  onRunKeyframe: (animation: CharacterAnimationData) => void;
  onRunKeyframeClick?: () => void;
}

export default function KeyframeSettings({
  jsonInput,
  onJsonInputChange,
  error,
  onError,
  onRunKeyframe,
  onRunKeyframeClick,
}: KeyframeSettingsProps) {
  const handle_run = () => {
    onError('');
    try {
      const trimmed = jsonInput.trim();
      if (!trimmed) {
        onError('JSONを入力してください。');
        return;
      }
      const parsed = parse_character_animation_json(trimmed);
      onRunKeyframe(parsed);
      onRunKeyframeClick?.();
    } catch (err) {
      onError(
        err instanceof Error ? err.message : 'JSONのパースに失敗しました。'
      );
    }
  };

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Film className="w-4 h-4" />
        Keyframe
      </h3>
      <label className="block text-xs font-medium text-gray-700 mb-2">
        VRM keyframe test (greetings.json)
      </label>
      <p className="text-xs text-gray-500 mb-2">
        name, duration, keyframes のJSONでVRMを制御
      </p>
      <textarea
        value={jsonInput}
        onChange={(e) => {
          onJsonInputChange(e.target.value);
          onError('');
        }}
        placeholder={SAMPLE_JSON}
        className="w-full h-24 p-2 border border-gray-300 rounded-md font-mono text-xs resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
        spellCheck={false}
      />
      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
      <button
        type="button"
        onClick={handle_run}
        className="w-full mt-2 px-3 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-md transition-colors"
      >
        Run keyframe
      </button>
      <p className="text-xs text-gray-500 mt-1.5">
        実行成功時はControlsタブに遷移します。
      </p>
    </div>
  );
}

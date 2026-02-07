'use client';

import React, { useState, useCallback } from 'react';
import { X } from 'lucide-react';

export interface CharacterAnimationKeyframe {
  time: number;
  bones?: Record<
    string,
    {
      rotation: { x: number; y: number; z: number };
    }
  >;
  expressions?: Record<string, number>;
}

export interface CharacterAnimationData {
  name: string;
  duration: number;
  keyframes: CharacterAnimationKeyframe[];
}

export interface CharacterControlModalProps {
  is_open: boolean;
  on_close: () => void;
  on_apply_control: (data: CharacterAnimationData) => void;
}

function parse_character_animation_json(json_string: string): CharacterAnimationData {
  const parsed = JSON.parse(json_string) as Record<string, unknown>;

  let animation: CharacterAnimationData;

  if (parsed.animations && Array.isArray(parsed.animations) && parsed.animations.length > 0) {
    const first = parsed.animations[0] as Record<string, unknown>;
    animation = {
      name: (first.name as string) ?? 'animation',
      duration: (first.duration as number) ?? 2000,
      keyframes: (first.keyframes as CharacterAnimationKeyframe[]) ?? [],
    };
  } else if (parsed.keyframes && Array.isArray(parsed.keyframes)) {
    animation = {
      name: (parsed.name as string) ?? 'animation',
      duration: (parsed.duration as number) ?? 2000,
      keyframes: parsed.keyframes as CharacterAnimationKeyframe[],
    };
  } else {
    throw new Error('キーフレーム形式のJSONが必要です。name, duration, keyframes を含めてください。');
  }

  if (!animation.keyframes || animation.keyframes.length === 0) {
    throw new Error('keyframes が空または無効です。');
  }

  return animation;
}

const SAMPLE_JSON = `{
  "name": "greeting",
  "duration": 2000,
  "keyframes": [
    {
      "time": 0,
      "bones": {
        "rightUpperArm": { "rotation": { "x": 0, "y": 0, "z": 0 } },
        "rightLowerArm": { "rotation": { "x": 0, "y": 0, "z": 0 } },
        "head": { "rotation": { "x": 0, "y": 0, "z": 0 } }
      },
      "expressions": { "happy": 0, "neutral": 1 }
    },
    {
      "time": 600,
      "bones": {
        "rightUpperArm": { "rotation": { "x": 0, "y": 0, "z": -0.7 } },
        "rightLowerArm": { "rotation": { "x": -1.2, "y": 0, "z": 0 } },
        "head": { "rotation": { "x": 0.1, "y": -0.05, "z": 0 } }
      },
      "expressions": { "happy": 1, "neutral": 0 }
    },
    {
      "time": 2000,
      "bones": {
        "rightUpperArm": { "rotation": { "x": 0, "y": 0, "z": 0 } },
        "rightLowerArm": { "rotation": { "x": 0, "y": 0, "z": 0 } },
        "head": { "rotation": { "x": 0, "y": 0, "z": 0 } }
      },
      "expressions": { "happy": 0, "neutral": 1 }
    }
  ]
}`;

export default function CharacterControlModal({
  is_open,
  on_close,
  on_apply_control,
}: CharacterControlModalProps) {
  const [json_input, set_json_input] = useState('');
  const [error_message, set_error_message] = useState('');

  const handle_execute = useCallback(() => {
    set_error_message('');
    try {
      const trimmed = json_input.trim();
      if (!trimmed) {
        set_error_message('JSONを入力してください。');
        return;
      }
      const parsed = parse_character_animation_json(trimmed);
      on_apply_control(parsed);
      on_close();
    } catch (err) {
      set_error_message(
        err instanceof Error ? err.message : 'JSONのパースに失敗しました。'
      );
    }
  }, [json_input, on_apply_control, on_close]);

  const handle_back = useCallback(() => {
    set_error_message('');
    set_json_input('');
    on_close();
  }, [on_close]);

  if (!is_open) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold text-gray-800">キャラクターを操作する</h2>
          <button
            onClick={handle_back}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title="閉じる"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        <div className="p-4 flex-1 overflow-hidden flex flex-col gap-4">
          <p className="text-sm text-gray-600">
            greetings.json形式（name, duration, keyframes）のJSONを入力してVRMを制御します。
          </p>
          <textarea
            value={json_input}
            onChange={(e) => set_json_input(e.target.value)}
            placeholder={SAMPLE_JSON}
            className="w-full h-64 p-3 border border-gray-300 rounded-lg font-mono text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            spellCheck={false}
          />
          {error_message && (
            <p className="text-sm text-red-600">{error_message}</p>
          )}
        </div>

        <div className="flex gap-3 p-4 border-t">
          <button
            onClick={handle_execute}
            className="flex-1 px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-xl transition-colors"
          >
            実行する
          </button>
          <button
            onClick={handle_back}
            className="flex-1 px-6 py-3 bg-gray-500 hover:bg-gray-600 text-white font-medium rounded-xl transition-colors"
          >
            戻る
          </button>
        </div>
      </div>
    </div>
  );
}

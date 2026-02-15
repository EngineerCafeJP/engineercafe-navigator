/**
 * Types and utilities for greetings.json-style VRM keyframe animation.
 * Used by CharacterAvatar Settings Panel for keyframe test.
 */

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

export function parse_character_animation_json(json_string: string): CharacterAnimationData {
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

export const SAMPLE_JSON = `{
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

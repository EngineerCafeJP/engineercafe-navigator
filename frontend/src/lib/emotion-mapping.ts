/**
 * Centralized emotion mapping for VRM character expressions and animations.
 * Kept in sync with backend/utils/emotion_mapping.py (EXPRESSION_MAP, ANIMATION_MAP).
 *
 * @see backend/utils/emotion_mapping.py
 */

/** VRM 表情（Python SupportedExpression と同一） */
export type SupportedExpression =
  | 'neutral'
  | 'happy'
  | 'sad'
  | 'angry'
  | 'surprised'
  | 'relaxed';

/** public/animations/manifest.json の .vrma 一覧（Python SupportedAnimation と同一） */
export type SupportedAnimation =
  | 'idle'
  | 'bowing'
  | 'greeting'
  | 'looking'
  | 'surprised'
  | 'talking'
  | 'thinking';

/** VRM 表情 6 種（バックエンド get_supported_expressions と同順） */
export const CANONICAL_EXPRESSIONS: readonly SupportedExpression[] = [
  'neutral',
  'happy',
  'sad',
  'angry',
  'surprised',
  'relaxed',
] as const;

export interface EmotionMappingConfig {
  /** 感情タグ → VRM 表情 */
  expressionMap: Record<string, SupportedExpression>;
  /** 感情タグ → アニメーション（感情キーで参照、表情経由ではない） */
  animationMap: Record<string, SupportedAnimation>;
  /** VRM 表情ごとの強度（バックエンドと同様 1.0 固定） */
  intensities: Record<SupportedExpression, number>;
}

export class EmotionMapping {
  /** emotion → VRM 表情（backend EXPRESSION_MAP） */
  static readonly EXPRESSION_MAP: Record<string, SupportedExpression> = {
    happy: 'happy',
    excited: 'happy',
    sad: 'sad',
    angry: 'angry',
    relaxed: 'relaxed',
    surprised: 'surprised',
    apologetic: 'sad',
    informative: 'relaxed',
    guiding: 'relaxed',
    helpful: 'happy',
    neutral: 'neutral',
    serious: 'sad',
    confident: 'relaxed',
    grateful: 'happy',
    confused: 'sad',
  };

  /** emotion → SupportedAnimation（backend ANIMATION_MAP） */
  static readonly ANIMATION_MAP: Record<string, SupportedAnimation> = {
    neutral: 'idle',
    happy: 'greeting',
    excited: 'greeting',
    sad: 'thinking',
    angry: 'talking',
    relaxed: 'thinking',
    surprised: 'surprised',
    apologetic: 'thinking',
    informative: 'talking',
    guiding: 'talking',
    helpful: 'greeting',
    serious: 'thinking',
    confident: 'talking',
    grateful: 'greeting',
    confused: 'thinking',
  };

  static readonly DEFAULT_EXPRESSION: SupportedExpression = 'neutral';
  static readonly DEFAULT_ANIMATION: SupportedAnimation = 'idle';
  static readonly DEFAULT_INTENSITY = 1.0;

  /**
   * 任意の感情文字列をサポート VRM 表情へ（backend map_to_expression）
   */
  static mapToExpression(emotion: string | unknown): SupportedExpression {
    if (!emotion || typeof emotion !== 'string') {
      console.warn('[EmotionMapping] Invalid emotion:', emotion, 'type:', typeof emotion);
      return this.DEFAULT_EXPRESSION;
    }
    const normalized = emotion.toLowerCase().trim();
    return this.EXPRESSION_MAP[normalized] ?? this.DEFAULT_EXPRESSION;
  }

  /**
   * 感情タグからアニメーション名（backend get_animation_for_emotion）
   * ANIMATION_MAP を expression キーで直接参照する。
   */
  static mapToAnimation(emotion: string): SupportedAnimation {
    if (!emotion || typeof emotion !== 'string') {
      return this.DEFAULT_ANIMATION;
    }
    const normalized = emotion.toLowerCase().trim();
    return this.ANIMATION_MAP[normalized] ?? this.DEFAULT_ANIMATION;
  }

  /**
   * 表情強度（backend get_intensity_for_expression — 常に固定値）
   */
  static getIntensityForExpression(_expression: string): number {
    return this.DEFAULT_INTENSITY;
  }
  
  static getSupportedExpressions(): SupportedExpression[] {
    return [...CANONICAL_EXPRESSIONS];
  }

  static getConfig(): EmotionMappingConfig {
    const intensities = {} as Record<SupportedExpression, number>;
    for (const e of CANONICAL_EXPRESSIONS) {
      intensities[e] = this.DEFAULT_INTENSITY;
    }
    return {
      expressionMap: { ...this.EXPRESSION_MAP },
      animationMap: { ...this.ANIMATION_MAP },
      intensities,
    };
  }

  /**
   * 正規化（backend normalize_emotion — intensity 引数は互換のため無視し常に 1.0）
   */
  static normalizeExpression(emotion: string, _intensity?: number): {
    expression: SupportedExpression;
    intensity: number;
  } {
    return {
      expression: this.mapToExpression(emotion),
      intensity: this.DEFAULT_INTENSITY,
    };
  }
}

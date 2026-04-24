import {
  CANONICAL_EXPRESSIONS,
  EmotionMapping,
  type SupportedExpression,
} from './emotion-mapping';

/**
 * Emotion Tag Parser for VRM character expression control
 * Parses emotion tags like [happy], [sad], [apologetic] from AI responses.
 * Tag keys must exist in EmotionMapping.EXPRESSION_MAP (aligned with backend).
 */

export interface ParsedResponse {
  cleanText: string;
  emotions: EmotionTag[];
  primaryEmotion?: string;
}

export interface EmotionTag {
  emotion: string;
  position: number;
  intensity?: number;
}

export class EmotionTagParser {
  /** EXPRESSION_MAP のキーとして解釈できるか（タグ名サポート判定） */
  private static isExpressionMapKey(raw: string): boolean {
    const key = raw.toLowerCase().trim();
    return key !== '' && key in EmotionMapping.EXPRESSION_MAP;
  }

  /**
   * Parse emotion tags from text
   */
  static parseEmotionTags(text: string): ParsedResponse {
    const emotionRegex = /\[\/?([a-zA-Z_]+)(?::(\d*\.?\d+))?\]/g;
    const emotions: EmotionTag[] = [];

    let match;
    while ((match = emotionRegex.exec(text)) !== null) {
      const tagName = match[1].toLowerCase();
      const intensityStr = match[2];
      const intensity = intensityStr ? parseFloat(intensityStr) : 1.0;
      const position = match.index;

      if (this.isExpressionMapKey(tagName)) {
        const mapped = EmotionMapping.mapToExpression(tagName);
        emotions.push({
          emotion: mapped,
          position,
          intensity: Math.max(0, Math.min(1, intensity)),
        });
      } else {
        console.warn(`Unknown emotion tag: [${tagName}]`);
      }
    }

    let cleanText = text.replace(emotionRegex, '').trim();
    cleanText = cleanText.replace(/\s+/g, ' ').trim();

    let primaryEmotion: string | undefined;
    if (emotions.length > 0) {
      const sortedEmotions = [...emotions].sort(
        (a, b) => (b.intensity || 1) - (a.intensity || 1),
      );
      primaryEmotion = sortedEmotions[0].emotion;
    }

    return {
      cleanText,
      emotions,
      primaryEmotion,
    };
  }

  /**
   * Get VRM expression weights for given emotion (canonical 6 keys)
   */
  static getExpressionWeights(emotion: string, intensity: number = 1.0): Record<string, number> {
    const weights: Record<string, number> = {};
    for (const e of CANONICAL_EXPRESSIONS) {
      weights[e] = 0;
    }

    const normalizedEmotion = EmotionMapping.mapToExpression(emotion);
    const normalizedIntensity = Math.max(0, Math.min(1, intensity));

    if (normalizedEmotion === 'neutral') {
      weights.neutral = 1;
    } else {
      weights[normalizedEmotion] = normalizedIntensity;
      weights.neutral = 1 - normalizedIntensity;
    }

    return weights;
  }

  /**
   * Create sample text with emotion tags for testing
   */
  static createSampleEmotionalText(language: 'ja' | 'en' = 'ja'): string {
    if (language === 'ja') {
      return '[happy]はじめまして！[neutral]今日はとても良い天気ですね。[relaxed]ところで、何かお手伝いできることはありますか？[/relaxed]';
    }
    return "[happy]Hello there! [neutral]It's such a beautiful day today. [relaxed]By the way, is there anything I can help you with?[/relaxed]";
  }

  /**
   * Validate if emotion tag name is in EXPRESSION_MAP
   */
  static isValidEmotion(emotion: string): boolean {
    return this.isExpressionMapKey(emotion);
  }

  /**
   * All tag aliases (keys of EXPRESSION_MAP)
   */
  static getSupportedEmotions(): string[] {
    return Object.keys(EmotionMapping.EXPRESSION_MAP);
  }

  /**
   * Canonical VRM expression names (6)
   */
  static getVRMExpressions(): SupportedExpression[] {
    return [...CANONICAL_EXPRESSIONS];
  }

  /**
   * Auto-add emotion tags to AI responses based on content analysis
   */
  static addEmotionTags(text: string, language: 'ja' | 'en' = 'ja'): string {
    if (text.includes('[') && text.includes(']')) {
      return text;
    }

    const lowerText = text.toLowerCase();
    let tagKey = 'neutral';

    if (language === 'ja') {
      if (
        lowerText.includes('ようこそ') ||
        lowerText.includes('はじめまして') ||
        lowerText.includes('ありがとう') ||
        lowerText.includes('素晴らしい')
      ) {
        tagKey = 'happy';
      } else if (
        lowerText.includes('申し訳') ||
        lowerText.includes('すみません') ||
        lowerText.includes('残念') ||
        lowerText.includes('困り')
      ) {
        tagKey = 'sad';
      } else if (
        lowerText.includes('考え') ||
        lowerText.includes('うーん') ||
        lowerText.includes('どうしよう') ||
        lowerText.includes('リラックス')
      ) {
        tagKey = 'relaxed';
      } else if (
        lowerText.includes('びっくり') ||
        lowerText.includes('驚き') ||
        lowerText.includes('すごい') ||
        lowerText.includes('まさか')
      ) {
        tagKey = 'surprised';
      } else if (
        lowerText.includes('問題') ||
        lowerText.includes('怒り') ||
        lowerText.includes('イライラ')
      ) {
        tagKey = 'angry';
      }
    } else {
      if (
        lowerText.includes('welcome') ||
        lowerText.includes('hello') ||
        lowerText.includes('great') ||
        lowerText.includes('wonderful') ||
        lowerText.includes('thank')
      ) {
        tagKey = 'happy';
      } else if (
        lowerText.includes('sorry') ||
        lowerText.includes('apologize') ||
        lowerText.includes('unfortunately') ||
        lowerText.includes('problem')
      ) {
        tagKey = 'sad';
      } else if (
        lowerText.includes('think') ||
        lowerText.includes('consider') ||
        lowerText.includes('hmm') ||
        lowerText.includes('relax')
      ) {
        tagKey = 'relaxed';
      } else if (
        lowerText.includes('wow') ||
        lowerText.includes('amazing') ||
        lowerText.includes('surprised') ||
        lowerText.includes('incredible')
      ) {
        tagKey = 'surprised';
      } else if (
        lowerText.includes('angry') ||
        lowerText.includes('frustrated') ||
        lowerText.includes('annoying')
      ) {
        tagKey = 'angry';
      }
    }

    return `[${tagKey}]${text}[/${tagKey}]`;
  }

  /**
   * Auto-enhance agent responses with appropriate emotion tags
   */
  static enhanceAgentResponse(
    response: string,
    context?: 'welcome' | 'qa' | 'error' | 'success',
    language: 'ja' | 'en' = 'ja',
  ): string {
    if (response.includes('[') && response.includes(']')) {
      return response;
    }

    let tagKey = 'neutral';

    switch (context) {
      case 'welcome':
        tagKey = 'happy';
        break;
      case 'qa':
        tagKey = 'neutral';
        break;
      case 'error':
        tagKey = 'sad';
        break;
      case 'success':
        tagKey = 'happy';
        break;
      default:
        return this.addEmotionTags(response, language);
    }

    return `[${tagKey}]${response}[/${tagKey}]`;
  }
}

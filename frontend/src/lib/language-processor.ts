/**
 * LanguageProcessor - 言語検出と応答言語決定
 */

import { SupportedLanguage } from '@/mastra/types/config';

export interface LanguageDetectionResult {
  detected: SupportedLanguage;
  confidence: number;
}

export class LanguageProcessor {
  /**
   * クエリの言語を検出
   */
  detectLanguage(query: string): LanguageDetectionResult {
    // 日本語文字（ひらがな、カタカナ、漢字）が含まれているかチェック
    const japaneseRegex = /[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/;
    const hasJapanese = japaneseRegex.test(query);

    if (hasJapanese) {
      return {
        detected: 'ja',
        confidence: 0.95
      };
    }

    // デフォルトは英語
    return {
      detected: 'en',
      confidence: 0.8
    };
  }

  /**
   * 応答言語を決定
   */
  determineResponseLanguage(languageResult: LanguageDetectionResult): SupportedLanguage {
    return languageResult.detected;
  }
}

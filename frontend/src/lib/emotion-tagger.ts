/**
 * Unified Emotion Tagging System
 * Ensures consistent emotion tags across all agents
 * 
 * Supported expressions: neutral, happy, angry, sad, relaxed, surprised
 */

export type SupportedExpression = 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised';

interface ExpressionRule {
  patterns: string[];
  expression: SupportedExpression;
  priority: number; // Higher priority rules override lower ones
}

export class EmotionTagger {
  private static readonly EXPRESSION_RULES: ExpressionRule[] = [
    // Happy patterns (priority: 8)
    {
      patterns: ['はじめまして', 'ようこそ', 'いらっしゃい', 'こんにちは', 'hello', 'welcome', 'nice to meet'],
      expression: 'happy',
      priority: 8
    },
    {
      patterns: ['！', '!', 'ありがとう', 'thank', '嬉しい', 'happy', '楽しい', 'fun', '素晴らしい', 'wonderful'],
      expression: 'happy',
      priority: 7
    },
    {
      patterns: ['お手伝い', 'help', 'どうぞ', 'please', 'ご利用', 'サービス', 'service'],
      expression: 'happy',
      priority: 6
    },
    
    // Sad patterns (priority: 9 - highest for apologies)
    {
      patterns: ['申し訳', 'すみません', 'ごめん', 'sorry', 'apologize', '残念', 'unfortunately'],
      expression: 'sad',
      priority: 9
    },
    {
      patterns: ['できません', 'できない', 'cannot', "can't", '無理', 'impossible'],
      expression: 'sad',
      priority: 7
    },
    
    // Angry patterns (priority: 5)
    {
      patterns: ['だめ', '禁止', 'forbidden', 'prohibited', '違反', 'violation'],
      expression: 'angry',
      priority: 5
    },
    
    // Surprised patterns (priority: 7)
    {
      patterns: ['どちら', 'どれ', 'which', '選んで', 'choose', '？', '?', 'それとも', 'or'],
      expression: 'surprised',
      priority: 7
    },
    {
      patterns: ['えっ', 'え？', 'what', 'really', '本当', 'まさか', 'びっくり'],
      expression: 'surprised',
      priority: 8
    },
    
    // Relaxed patterns (priority: 4)
    {
      patterns: ['説明', 'について', 'とは', 'explain', 'about', '詳細', 'details'],
      expression: 'relaxed',
      priority: 4
    },
    {
      patterns: ['営業時間', '料金', '場所', 'hours', 'price', 'location', '設備', 'facility'],
      expression: 'relaxed',
      priority: 3
    },
  ];

  /**
   * Add emotion tags to response text
   * 
   * @param text - The response text
   * @param forceEmotion - Optional emotion to force (overrides detection)
   * @returns Text with emotion tag prepended
   */
  static addEmotionTag(text: string, forceExpression?: SupportedExpression): string {
    if (!text || text.trim().length === 0) {
      return text;
    }

    // Check if emotion tag already exists
    const hasEmotionTag = /^\[[a-zA-Z_]+(?::\d*\.?\d+)?\]/.test(text.trim());
    if (hasEmotionTag) {
      return text;
    }

    // Use forced emotion if provided
    const expression = forceExpression || this.getExpressionFromText(text);
    return `[${expression}]${text}`;
  }

  /**
   * Detect emotion from text content
   * 
   * @param text - The text to analyze
   * @returns Detected emotion
   */
  static getExpressionFromText(text: string): SupportedExpression {
    const lowerText = text.toLowerCase();
    let detectedExpression: SupportedExpression = 'neutral' as SupportedExpression;
    let highestPriority = -1;

    // Check all rules and use the highest priority match
    for (const rule of this.EXPRESSION_RULES) {
      if (rule.priority > highestPriority) {
        for (const pattern of rule.patterns) {
          if (lowerText.includes(pattern.toLowerCase())) {
            detectedExpression = rule.expression;
            highestPriority = rule.priority;
            break;
          }
        }
      }
    }

    // Default fallback
    if (highestPriority === -1) {
      // For informational content, use relaxed
      if (text.length > 100) {
        return 'relaxed' as SupportedExpression;
      }
      // For short responses, default to neutral (which maps to happy)
      return 'happy' as SupportedExpression;
    }

    return detectedExpression;
  }

  /**
   * Update emotion mapping to use 5 standard emotions
   * Maps neutral to happy for more positive interactions
   */
  static normalizeExpression(emotion: string): SupportedExpression {
    const emotionMap: Record<string, SupportedExpression> = {
      // Direct mappings
      'happy': 'happy',
      'angry': 'angry',
      'sad': 'sad',
      'relaxed': 'relaxed',
      'surprised': 'surprised',
      
      // Common aliases
      'neutral': 'happy', // Make neutral more positive
      'curious': 'surprised',
      'excited': 'happy',
      'helpful': 'happy',
      'apologetic': 'sad',
      'thoughtful': 'relaxed',
      'explaining': 'relaxed',
      'confused': 'surprised',
      'welcoming': 'happy',
      'greeting': 'happy',
    };

    return emotionMap[emotion.toLowerCase()] || 'happy' as SupportedExpression;
  }

  /**
   * Extract existing emotion from tagged text
   * 
   * @param text - Text that may contain emotion tags
   * @returns Extracted emotion or null
   */
  static extractExpression(text: string): SupportedExpression | null {
    const match = text.match(/^\[([a-zA-Z_]+)(?::\d*\.?\d+)?\]/);
    if (match) {
      return this.getExpressionFromText(match[1]);
    }
    return null;
  }

  /**
   * Remove emotion tags from text
   * 
   * @param text - Text with emotion tags
   * @returns Clean text without tags
   */
  static removeEmotionTags(text: string): string {
    return text.replace(/\[\/?\w+(?::\d*\.?\d+)?\]/g, '').trim();
  }

  /**
   * Get emotion for specific agent contexts
   * 
   * @param agentName - Name of the agent
   * @param category - Response category
   * @returns Appropriate emotion
   */
  static getExpressionForContext(agentName: string, category?: string): SupportedExpression {
    // Agent-specific emotions
    const contextMap: Record<string, SupportedExpression> = {
      // ClarificationAgent - always curious/surprised
      'ClarificationAgent': 'surprised',
      
      // WelcomeAgent - always happy
      'WelcomeAgent': 'happy',
      
      // MemoryAgent contexts
      'memory-found': 'happy',
      'memory-not-found': 'sad',
      
      // EventAgent contexts
      'events-found': 'happy',
      'no-events': 'relaxed',
      
      // FacilityAgent contexts
      'facility-available': 'happy',
      'facility-unavailable': 'sad',
      
      // Error contexts
      'error': 'sad',
      'not-found': 'sad',
    };

    const key = category ? `${agentName}-${category}` : agentName;
    return contextMap[key] || contextMap[agentName] || 'relaxed' as SupportedExpression;
  }
}
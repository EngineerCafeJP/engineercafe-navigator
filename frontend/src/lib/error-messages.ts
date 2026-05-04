/**
 * Bilingual error messages for user-friendly error handling
 */

export interface ErrorMessage {
  ja: string;
  en: string;
}

export const ERROR_MESSAGES: Record<string, ErrorMessage> = {
  // Voice Processing Errors
  MICROPHONE_PERMISSION_DENIED: {
    ja: 'マイクへのアクセスが拒否されました。ブラウザの設定でマイクへのアクセスを許可してください。',
    en: 'Microphone access was denied. Please allow microphone access in your browser settings.',
  },
  MIC_PERMISSION_DENIED: {
    ja:
      'マイクの許可が必要です。ブラウザのアドレスバー付近の鍵／許可アイコンからマイクを「許可」に変更するか、設定でこのサイトのマイクをオンにしてください。変更後はもう一度マイクボタンを押してください。',
    en:
      'Microphone permission is required. Use the lock or site-settings icon in the address bar to allow the microphone for this site, then tap the mic button again.',
  },
  MIC_NOT_FOUND: {
    ja:
      'マイクが見つかりません。ケーブルやBluetoothの接続を確認し、他のアプリがマイクを占有していないか確認してから、もう一度お試しください。',
    en:
      'No microphone was found. Check your cable or Bluetooth connection, make sure no other app is using the mic, then try again.',
  },
  MIC_NOT_FOUND_IOS: {
    ja:
      '画面録画中、別アプリで通話中、または Safari の Web サイト設定でマイクが拒否されている可能性があります。画面録画を停止し、設定 → Safari → Web サイト → マイクで「許可」になっているか確認してから、もう一度お試しください。',
    en:
      'iPhone may be screen recording, another app is using the microphone, or Safari has blocked microphone access. Stop screen recording and check Settings → Safari → Websites → Microphone, then try again.',
  },
  MIC_INVALID_STATE: {
    ja:
      'マイクの状態が不正です（録音パイプラインの競合など）。タブを開き直すかページを再読み込みしてから、もう一度マイクボタンを押してください。',
    en:
      'The microphone is in an invalid state (recording pipeline conflict). Reload the page or reopen the tab, then press the mic button again.',
  },
  MIC_SECURITY_ERROR: {
    ja:
      'セキュリティ制限によりマイクにアクセスできません。HTTPS または localhost で開いているか確認してください。',
    en:
      'Microphone access is blocked for security reasons. Open this page over HTTPS or on localhost.',
  },
  MICROPHONE_NOT_FOUND: {
    ja: 'マイクが検出されませんでした。マイクが正しく接続されているか確認してください。',
    en: 'No microphone was detected. Please check that your microphone is properly connected.',
  },
  MICROPHONE_IN_USE: {
    ja: 'マイクが他のアプリに使用されています。他のアプリを閉じてからもう一度お試しください。',
    en: 'The microphone is being used by another app. Please close other apps and try again.',
  },
  MICROPHONE_START_FAILED: {
    ja: 'マイクの起動に失敗しました。もう一度ボタンをタップしてください。',
    en: 'Failed to start the microphone. Please tap the button again.',
  },
  VOICE_PROCESSING_ERROR: {
    ja: '音声の処理中にエラーが発生しました。もう一度お試しください。',
    en: 'An error occurred while processing your voice. Please try again.',
  },
  SPEECH_RECOGNITION_ERROR: {
    ja: '音声認識に失敗しました。もう一度はっきりと話してください。',
    en: 'Speech recognition failed. Please speak clearly and try again.',
  },
  
  // Network Errors
  NETWORK_ERROR: {
    ja: 'ネットワーク接続に問題があります。インターネット接続を確認してください。',
    en: 'There is a network connection problem. Please check your internet connection.',
  },
  SERVER_ERROR: {
    ja: 'サーバーエラーが発生しました。しばらくしてからもう一度お試しください。',
    en: 'A server error occurred. Please try again later.',
  },
  SERVICE_UNAVAILABLE: {
    ja: 'サービスが一時的に利用できません。しばらくしてからもう一度お試しください。',
    en: 'Service is temporarily unavailable. Please try again later.',
  },
  BACKEND_TIMEOUT: {
    ja:
      '音声サービスの起動に時間がかかっています。少し待ってからもう一度お試しください。',
    en:
      'The voice service is still warming up. Please wait a moment and try again.',
  },
  
  // Session Errors
  SESSION_EXPIRED: {
    ja: 'セッションの有効期限が切れました。ページを更新してください。',
    en: 'Your session has expired. Please refresh the page.',
  },
  SESSION_NOT_FOUND: {
    ja: 'セッションが見つかりません。ページを更新してください。',
    en: 'Session not found. Please refresh the page.',
  },
  
  // Character/Model Errors
  CHARACTER_LOAD_ERROR: {
    ja: 'キャラクターの読み込みに失敗しました。ページを更新してください。',
    en: 'Failed to load character. Please refresh the page.',
  },
  WEBGL_NOT_SUPPORTED: {
    ja: 'お使いのブラウザはWebGLをサポートしていません。最新のブラウザをご利用ください。',
    en: 'Your browser does not support WebGL. Please use a modern browser.',
  },
  
  // Slide Errors
  SLIDE_NOT_FOUND: {
    ja: 'スライドが見つかりませんでした。',
    en: 'Slide not found.',
  },
  SLIDE_LOAD_ERROR: {
    ja: 'スライドの読み込みに失敗しました。',
    en: 'Failed to load slide.',
  },
  
  // API Errors
  STT_ERROR: {
    ja: '音声認識処理でエラーが発生しました。',
    en: 'Speech recognition processing failed.',
  },
  QA_ERROR: {
    ja: '質問の送信に失敗しました。もう一度お試しください。',
    en: 'Failed to send question. Please try again.',
  },
  TTS_ERROR: {
    ja: '音声の生成に失敗しました。',
    en: 'Voice generation failed.',
  },
  VALIDATION_ERROR: {
    ja: 'リクエストの形式が正しくありません。',
    en: 'Invalid request format.',
  },
  API_KEY_INVALID: {
    ja: 'APIキーが無効です。設定を確認してください。',
    en: 'Invalid API key. Please check your configuration.',
  },
  RATE_LIMIT_EXCEEDED: {
    ja: '利用制限に達しました。しばらくしてからもう一度お試しください。',
    en: 'Rate limit exceeded. Please try again later.',
  },
  
  // Generic Errors
  UNKNOWN_ERROR: {
    ja: '予期しないエラーが発生しました。もう一度お試しください。',
    en: 'An unexpected error occurred. Please try again.',
  },
  NOT_SUPPORTED: {
    ja: 'この機能はお使いのブラウザではサポートされていません。',
    en: 'This feature is not supported in your browser.',
  },
};

/** True when running on iPhone/iPad/iPod Safari or iPad-as-desktop (Mac UA + touch). */
export function isIOSUserAgent(): boolean {
  if (typeof navigator === 'undefined') {
    return false;
  }
  const ua =
    typeof navigator.userAgent === 'string' ? navigator.userAgent : '';
  return (
    /iPad|iPhone|iPod/.test(ua) ||
    (ua.includes('Mac') && navigator.maxTouchPoints > 1)
  );
}

/**
 * Get error message in specified language
 */
export function getErrorMessage(
  errorCode: string,
  language: 'ja' | 'en' = 'ja'
): string {
  const message = ERROR_MESSAGES[errorCode];
  if (!message) {
    return ERROR_MESSAGES.UNKNOWN_ERROR[language];
  }
  return message[language];
}

/**
 * Format error for display
 */
export function formatError(
  error: any,
  language: 'ja' | 'en' = 'ja'
): string {
  const errorName = String(error?.originalName ?? error?.name ?? '').toLowerCase();
  if (errorName) {
    switch (errorName) {
      case 'notallowederror':
      case 'permissiondeniederror':
        return getErrorMessage('MIC_PERMISSION_DENIED', language);
      case 'securityerror':
        return getErrorMessage('MIC_SECURITY_ERROR', language);
      case 'notfounderror':
      case 'devicesnotfounderror':
      case 'overconstrainederror':
        return getErrorMessage(
          isIOSUserAgent() ? 'MIC_NOT_FOUND_IOS' : 'MIC_NOT_FOUND',
          language,
        );
      case 'notreadableerror':
      case 'trackstarterror':
        return getErrorMessage('MICROPHONE_IN_USE', language);
      case 'invalidstateerror':
        return getErrorMessage('MIC_INVALID_STATE', language);
    }
  }

  // Check for known error codes
  if (error.code && ERROR_MESSAGES[error.code]) {
    return getErrorMessage(error.code, language);
  }
  
  // Check for API-specific error patterns
  if (error.message) {
    const message = String(error.message).toLowerCase();
    if (
      message.includes('音声認識に失敗') ||
      message.includes('speech recognition')
    ) {
      return getErrorMessage('STT_ERROR', language);
    }
    if (
      message.includes('質問の送信に失敗') ||
      message.includes('send question') ||
      message.includes('chat')
    ) {
      return getErrorMessage('QA_ERROR', language);
    }
    if (
      message.includes('音声の生成に失敗') ||
      message.includes('voice generation') ||
      message.includes('text_to_speech')
    ) {
      return getErrorMessage('TTS_ERROR', language);
    }
    if (
      message.includes('timed out') ||
      message.includes('timeout') ||
      message.includes('504')
    ) {
      return getErrorMessage('BACKEND_TIMEOUT', language);
    }
  }

  // Check for 422 validation error
  if (error.status === 422) {
    return getErrorMessage('VALIDATION_ERROR', language);
  }

  // Check for specific error messages
  if (error.message) {
    const message = String(error.message).toLowerCase();
    if (message.includes('not supported') || message.includes('not available')) {
      return getErrorMessage('NOT_SUPPORTED', language);
    }
    if (
      message.includes('microphone') ||
      message.includes('getusermedia') ||
      message.includes('mediarecorder') ||
      message.includes('recorder')
    ) {
      if (
        message.includes('not found') ||
        message.includes('no microphone') ||
        message.includes('unavailable')
      ) {
        return getErrorMessage('MICROPHONE_NOT_FOUND', language);
      }
      if (message.includes('in use') || message.includes('not readable')) {
        return getErrorMessage('MICROPHONE_IN_USE', language);
      }
      if (
        message.includes('invalidstate') ||
        message.includes('already recording') ||
        message.includes('failed to start')
      ) {
        return getErrorMessage('MICROPHONE_START_FAILED', language);
      }
      return getErrorMessage('MICROPHONE_PERMISSION_DENIED', language);
    }
    if (message.includes('network') || message.includes('fetch')) {
      return getErrorMessage('NETWORK_ERROR', language);
    }
    if (message.includes('rate limit')) {
      return getErrorMessage('RATE_LIMIT_EXCEEDED', language);
    }
  }
  
  // Check for HTTP status codes
  if (error.status) {
    if (error.status === 504) {
      return getErrorMessage('BACKEND_TIMEOUT', language);
    }
    if (error.status >= 500) {
      return getErrorMessage('SERVER_ERROR', language);
    }
    if (error.status === 429) {
      return getErrorMessage('RATE_LIMIT_EXCEEDED', language);
    }
    if (error.status === 403) {
      return getErrorMessage('API_KEY_INVALID', language);
    }
  }
  
  // Default to unknown error
  return getErrorMessage('UNKNOWN_ERROR', language);
}

/**
 * Error notification component props
 */
export interface ErrorNotificationProps {
  error: any;
  language: 'ja' | 'en';
  onClose?: () => void;
  autoClose?: boolean;
  autoCloseDelay?: number;
}

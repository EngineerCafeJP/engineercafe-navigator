/**
 * Mobile-friendly audio service
 * Provides fallback mechanisms and better error handling for mobile devices
 */

import { WebAudioPlayer } from './web-audio-player';
import { AudioInteractionManager } from './audio-interaction-manager';
import { AudioDataProcessor } from './audio-data-processor';
import { 
  AudioError, 
  AudioErrorType, 
  type AudioOperationResult,
  type AudioDataInput,
  type MobileAudioPlayerOptions
} from './audio-interfaces';

export interface MobileAudioOptions extends MobileAudioPlayerOptions {
  retryAttempts?: number;
  retryDelay?: number;
  largeAudioThresholdBytes?: number;
  decodeTimeoutMs?: number;
}

// Legacy type alias for backward compatibility
export type AudioPlaybackResult = AudioOperationResult;

export class MobileAudioService {
  private static readonly PLAYBACK_START_TIMEOUT_MS = 8000;
  private webAudioPlayer: WebAudioPlayer | null = null;
  private htmlAudioElement: HTMLAudioElement | null = null;
  private htmlAudioUrl: string | null = null;
  private detachHtmlAudioListeners: (() => void) | null = null;
  private interactionManager: AudioInteractionManager;
  private options: MobileAudioOptions;
  private currentMethod: 'web-audio' | 'html-audio' | null = null;

  constructor(options: MobileAudioOptions = {}) {
    this.options = {
      retryAttempts: 3,
      retryDelay: 1000,
      enableFallback: true,
      preferredMethod: 'auto',
      largeAudioThresholdBytes: AudioDataProcessor.LARGE_AUDIO_FALLBACK_THRESHOLD_BYTES,
      ...options
    };
    this.interactionManager = AudioInteractionManager.getInstance();
  }

  /**
   * Update event handlers for this instance
   */
  public updateEventHandlers(handlers: Partial<Pick<MobileAudioOptions, 'onPlay' | 'onEnded' | 'onError' | 'onPause'>>): void {
    this.options = { ...this.options, ...handlers };
  }

  /**
   * Load and play audio using Web Audio API only
   */
  public async playAudio(audioData: AudioDataInput): Promise<AudioOperationResult> {
    try {
      const result = await this.withPlaybackStartTimeout(async () => {
        if (this.shouldPreferHtmlAudio(audioData)) {
          const htmlAudioResult = await this.tryHtmlAudio(audioData);
          if (htmlAudioResult.success) {
            return htmlAudioResult;
          }

          if (this.options.preferredMethod === 'html-audio') {
            return htmlAudioResult;
          }

          console.warn('[MOBILE-AUDIO] HTML audio fallback failed, retrying Web Audio:', htmlAudioResult.error);
        }

        const webAudioResult = await this.tryWebAudio(audioData);
        if (
          !webAudioResult.success &&
          this.options.enableFallback !== false &&
          this.options.preferredMethod !== 'web-audio'
        ) {
          return this.tryHtmlAudio(audioData);
        }

        return webAudioResult;
      });
      if (result.success) {
        this.currentMethod = (result.method as 'web-audio' | 'html-audio' | null) ?? 'web-audio';
        return result;
      }
      
      const error = result.error || new AudioError(
        AudioErrorType.PLAYBACK_FAILED, 
        'Audio playback failed'
      );

      return {
        success: false,
        method: result.method ?? 'web-audio',
        error
      };
    } catch (error) {
      const audioError = AudioError.fromError(error as Error, AudioErrorType.PLAYBACK_FAILED);
      return {
        success: false,
        method: this.currentMethod ?? 'web-audio',
        error: audioError
      };
    }
  }

  private getAudioSize(audioData: AudioDataInput): number {
    try {
      return AudioDataProcessor.estimateAudioDataSize(audioData);
    } catch (error) {
      console.warn('[MOBILE-AUDIO] Failed to estimate audio size:', error);
      return 0;
    }
  }

  private shouldPreferHtmlAudio(audioData: AudioDataInput): boolean {
    if (this.options.preferredMethod === 'html-audio') {
      return true;
    }

    if (this.options.preferredMethod === 'web-audio' || this.options.enableFallback === false) {
      return false;
    }

    if (DeviceDetector.isIOS()) {
      return true;
    }

    const audioSize = this.getAudioSize(audioData);
    const threshold = this.options.largeAudioThresholdBytes ?? AudioDataProcessor.LARGE_AUDIO_FALLBACK_THRESHOLD_BYTES;
    const isLargeAudio = audioSize > threshold;
    const isUrlString =
      typeof audioData === 'string' &&
      (audioData.startsWith('blob:') || audioData.startsWith('http'));

    return DeviceDetector.isAndroid() && DeviceDetector.isMobile() && (isLargeAudio || isUrlString);
  }

  /**
   * Try Web Audio API playback
   * Uses AudioContext.decodeAudioData() - no HTMLAudioElement needed
   */
  private async tryWebAudio(audioData: AudioDataInput): Promise<AudioOperationResult> {
    try {
      const isTablet = /iPad|Android.*Tablet/i.test(navigator.userAgent);
      

      // Ensure audio context is ready
      try {
        await this.interactionManager.ensureAudioContext();
      } catch (error) {
        // If user interaction is required, let the UI handle it
        if (error instanceof Error && error.message.includes('User interaction required')) {
          throw new AudioError(
            AudioErrorType.USER_INTERACTION_REQUIRED,
            'User interaction required for audio playback',
            error as Error,
            true // requiresUserInteraction flag
          );
        } else {
          throw error;
        }
      }

      // For tablets, always recreate the player to avoid state issues
      if (!this.webAudioPlayer) {
        this.webAudioPlayer = new WebAudioPlayer(this.options);
      } else if (isTablet) {
        // Reset existing player for tablets to avoid state issues
        this.webAudioPlayer.reset();
      }

      // Load audio data using the new unified method
      const loadResult = await this.webAudioPlayer.loadAudioData(audioData);
      if (!loadResult.success) {
        return {
          success: false,
          method: 'web-audio',
          error: loadResult.error
        };
      }

      this.webAudioPlayer.setOptions(this.options);

      // Start audio playback
      const playResult = await this.webAudioPlayer.play();
      if (!playResult.success) {
        return playResult;
      }

      
      // Simply return success - let AudioPlaybackService handle the waiting
      return {
        success: true,
        method: 'web-audio'
      };
    } catch (error) {
      console.warn('[MOBILE-AUDIO] Web Audio playback failed:', error);
      const audioError = AudioError.fromError(error as Error, AudioErrorType.PLAYBACK_FAILED);
      return {
        success: false,
        method: 'web-audio',
        error: audioError
      };
    }
  }

  private async tryHtmlAudio(audioData: AudioDataInput): Promise<AudioOperationResult> {
    try {
      this.cleanupHtmlAudio();

      const shouldReuseUrl =
        typeof audioData === 'string' &&
        (audioData.startsWith('blob:') || audioData.startsWith('http'));
      const audioUrl = shouldReuseUrl ? audioData : URL.createObjectURL(await this.toAudioBlob(audioData));
      const audio = new Audio(audioUrl);
      audio.preload = 'auto';
      audio.volume = this.options.volume ?? 0.8;
      audio.setAttribute('playsinline', 'true');
      audio.setAttribute('webkit-playsinline', 'true');

      let didEmitPlay = false;
      const emitPlay = () => {
        if (didEmitPlay) {
          return;
        }
        didEmitPlay = true;
        this.options.onPlay?.();
      };

      const onPlay = () => emitPlay();
      const onPause = () => {
        if (!audio.ended) {
          this.options.onPause?.();
        }
      };
      const onEnded = () => {
        this.options.onEnded?.();
        this.cleanupHtmlAudio();
      };
      const onError = () => {
        const audioError = new AudioError(
          AudioErrorType.PLAYBACK_FAILED,
          'HTML audio playback failed on mobile',
        );
        this.options.onError?.(audioError);
        this.cleanupHtmlAudio();
      };

      audio.addEventListener('play', onPlay);
      audio.addEventListener('pause', onPause);
      audio.addEventListener('ended', onEnded);
      audio.addEventListener('error', onError);

      this.detachHtmlAudioListeners = () => {
        audio.removeEventListener('play', onPlay);
        audio.removeEventListener('pause', onPause);
        audio.removeEventListener('ended', onEnded);
        audio.removeEventListener('error', onError);
      };

      this.htmlAudioElement = audio;
      this.htmlAudioUrl = shouldReuseUrl ? null : audioUrl;

      await audio.play();
      emitPlay();

      return {
        success: true,
        method: 'html-audio',
      };
    } catch (error) {
      this.cleanupHtmlAudio();
      console.warn('[MOBILE-AUDIO] HTML audio playback failed:', error);
      const audioError = AudioError.fromError(error as Error, AudioErrorType.PLAYBACK_FAILED);
      return {
        success: false,
        method: 'html-audio',
        error: audioError,
      };
    }
  }

  private async toAudioBlob(audioData: AudioDataInput): Promise<Blob> {
    if (audioData instanceof Blob) {
      return audioData;
    }

    if (audioData instanceof ArrayBuffer) {
      const mimeType = AudioDataProcessor.detectAudioFormat(audioData);
      return new Blob([audioData], { type: mimeType });
    }

    const blobResult = await AudioDataProcessor.base64ToBlob(audioData);
    if (!blobResult.success || !blobResult.data) {
      throw new AudioError(
        AudioErrorType.INVALID_DATA,
        blobResult.error || 'Failed to convert base64 audio to Blob',
      );
    }

    return blobResult.data;
  }

  private async withPlaybackStartTimeout(
    runner: () => Promise<AudioOperationResult>
  ): Promise<AudioOperationResult> {
    let timeoutId: number | null = null;

    const timeoutPromise = new Promise<AudioOperationResult>((resolve) => {
      timeoutId = window.setTimeout(() => {
        this.stop();
        resolve({
          success: false,
          method: this.currentMethod ?? 'web-audio',
          error: new AudioError(
            AudioErrorType.PLAYBACK_FAILED,
            `Audio playback did not start within ${MobileAudioService.PLAYBACK_START_TIMEOUT_MS}ms`,
          ),
        });
      }, MobileAudioService.PLAYBACK_START_TIMEOUT_MS);
    });

    try {
      return await Promise.race([runner(), timeoutPromise]);
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  }

  private cleanupHtmlAudio(revokeUrl: boolean = true): void {
    if (this.detachHtmlAudioListeners) {
      this.detachHtmlAudioListeners();
      this.detachHtmlAudioListeners = null;
    }

    if (this.htmlAudioElement) {
      this.htmlAudioElement.pause();
      this.htmlAudioElement.removeAttribute('src');
      this.htmlAudioElement.load();
      this.htmlAudioElement = null;
    }

    if (revokeUrl && this.htmlAudioUrl) {
      URL.revokeObjectURL(this.htmlAudioUrl);
      this.htmlAudioUrl = null;
    }
  }



  // Removed helper methods - now using shared utilities from AudioDataProcessor and AudioError

  /**
   * Pause current playback
   */
  public pause(): void {
    if (this.htmlAudioElement) {
      this.htmlAudioElement.pause();
    }
    if (this.webAudioPlayer) {
      this.webAudioPlayer.pause();
    }
  }

  /**
   * Stop current playback
   */
  public stop(): void {
    this.cleanupHtmlAudio();

    if (this.webAudioPlayer) {
      this.webAudioPlayer.stop();
      
      // Reset for tablets to prevent state issues
      const isTablet = /iPad|Android.*Tablet/i.test(navigator.userAgent);
      if (isTablet) {
        this.webAudioPlayer.reset();
      }
    }
  }

  /**
   * Set volume
   */
  public setVolume(volume: number): void {
    this.options.volume = volume;
    if (this.htmlAudioElement) {
      this.htmlAudioElement.volume = volume;
    }
    if (this.webAudioPlayer) {
      this.webAudioPlayer.setVolume(volume);
    }
  }

  /**
   * Get current playback time
   */
  public getCurrentTime(): number {
    if (this.htmlAudioElement) {
      return this.htmlAudioElement.currentTime;
    }
    if (this.webAudioPlayer) {
      return this.webAudioPlayer.getCurrentTime();
    }
    return 0;
  }

  /**
   * Get duration
   */
  public getDuration(): number {
    if (this.htmlAudioElement) {
      return Number.isFinite(this.htmlAudioElement.duration) ? this.htmlAudioElement.duration : 0;
    }
    if (this.webAudioPlayer) {
      return this.webAudioPlayer.getDuration();
    }
    return 0;
  }

  /**
   * Check if playing
   */
  public isPlaying(): boolean {
    if (this.htmlAudioElement) {
      return !this.htmlAudioElement.paused && !this.htmlAudioElement.ended;
    }
    if (this.webAudioPlayer) {
      return this.webAudioPlayer.getIsPlaying();
    }
    return false;
  }

  /**
   * Get current playback method
   */
  public getCurrentMethod(): 'web-audio' | 'html-audio' | null {
    return this.currentMethod;
  }

  /**
   * Check if audio context is ready
   */
  public isAudioContextReady(): boolean {
    return this.interactionManager.isAudioContextReady();
  }

  /**
   * Cleanup resources
   */
  public dispose(): void {
    this.cleanupHtmlAudio();

    if (this.webAudioPlayer) {
      this.webAudioPlayer.dispose();
      this.webAudioPlayer = null;
    }

    this.currentMethod = null;
  }
}

/**
 * Detect device type for audio optimization
 */
export class DeviceDetector {
  public static isIOS(): boolean {
    return /iPad|iPhone|iPod/.test(navigator.userAgent);
  }

  public static isAndroid(): boolean {
    return /Android/.test(navigator.userAgent);
  }

  public static isMobile(): boolean {
    return this.isIOS() || this.isAndroid() || window.innerWidth <= 768;
  }

  public static isTablet(): boolean {
    return /iPad/.test(navigator.userAgent) || 
           (this.isAndroid() && window.innerWidth >= 768);
  }

  public static getSafariVersion(): number | null {
    const match = navigator.userAgent.match(/Version\/(\d+)/);
    return match ? parseInt(match[1], 10) : null;
  }

  public static supportsWebAudio(): boolean {
    return !!(window.AudioContext || (window as any).webkitAudioContext);
  }

  public static getRecommendedAudioMethod(): 'web-audio' | 'html-audio' {
    // iOS Safari has strict autoplay policies, Web Audio works better
    if (this.isIOS()) {
      return 'web-audio';
    }
    
    // Android decodeAudioData can hang on large payloads; prefer HTML Audio.
    if (this.isAndroid()) {
      return 'html-audio';
    }

    // Desktop - either works, Web Audio preferred for advanced features
    return 'web-audio';
  }
}

/**
 * Audio Queue for managing sequential audio playback
 * Handles TTS audio streaming and queueing using Web Audio API
 */

import { MobileAudioService } from './audio/mobile-audio-service';
import { AudioError, AudioErrorType } from './audio/audio-interfaces';

export interface AudioQueueItem {
  id: string;
  audioData: string; // base64 encoded audio
  text?: string;
  priority?: number;
  emotion?: string;
  /** Fired when underlying playback actually starts (after decode). */
  onPlaybackStart?: () => void;
  /** Fired when this clip ends or errors. */
  onPlaybackEnd?: () => void;
}

export class AudioQueue {
  private queue: AudioQueueItem[] = [];
  private isPlaying = false;
  private currentAudioService: MobileAudioService | null = null;
  private volume = 0.8;
  private onFinishedCallback?: () => void;
  private isSkipping = false;
  private currentPlaybackSettler: (() => void) | null = null;

  constructor() {
    // Initialize audio queue
  }

  /**
   * Set callback for when queue finishes playing
   */
  setOnFinished(callback: () => void): void {
    this.onFinishedCallback = callback;
  }

  /**
   * Add audio to the queue
   */
  add(item: AudioQueueItem): void {
    // Sort by priority (higher priority first)
    if (item.priority !== undefined) {
      const insertIndex = this.queue.findIndex(
        queueItem => (queueItem.priority ?? 0) < (item.priority ?? 0)
      );
      if (insertIndex === -1) {
        this.queue.push(item);
      } else {
        this.queue.splice(insertIndex, 0, item);
      }
    } else {
      this.queue.push(item);
    }

    // Start playing if not already playing
    if (!this.isPlaying) {
      this.playNext();
    }
  }

  /**
   * Clear the queue
   */
  clear(): void {
    this.queue = [];
    const settleCurrentPlayback = this.currentPlaybackSettler;
    this.currentPlaybackSettler = null;
    if (this.currentAudioService) {
      this.currentAudioService.stop();
      this.currentAudioService = null;
    }
    settleCurrentPlayback?.();
    this.isPlaying = false;
  }

  /**
   * Set volume for all audio
   */
  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(1, volume));
    // Volume will be applied to next audio service instance
  }

  /**
   * Get current queue size
   */
  getQueueSize(): number {
    return this.queue.length;
  }

  /**
   * Check if audio is currently playing
   */
  getIsPlaying(): boolean {
    return this.isPlaying;
  }

  /**
   * Play the next item in the queue
   */
  private async playNext(): Promise<void> {
    // Prevent concurrent playNext calls during skip operations
    if (this.isSkipping) {
      return;
    }
    
    if (this.queue.length === 0) {
      this.isPlaying = false;
      // Call finished callback if set
      if (this.onFinishedCallback) {
        this.onFinishedCallback();
      }
      return;
    }

    // Prevent multiple concurrent playNext calls
    if (this.isPlaying) {
      return;
    }

    this.isPlaying = true;
    const item = this.queue.shift();
    if (!item) {
      this.isPlaying = false;
      return;
    }

    try {
      await this.playAudio(item);
    } catch (error) {
      console.error('Error playing audio:', error);
    }

    // Continue with next item
    this.isPlaying = false; // Reset before recursive call
    setTimeout(() => {
      this.playNext();
    }, 0);
  }

  /**
   * Play a single audio item using Web Audio API
   */
  private async playAudio(item: AudioQueueItem): Promise<void> {
    return new Promise((resolve, reject) => {
      let settled = false;
      let resolveCurrentPlayback: (() => void) | null = null;

      let audioService: MobileAudioService | null = null;
      const settle = (complete: () => void): void => {
        if (settled) {
          return;
        }
        settled = true;
        if (this.currentPlaybackSettler === resolveCurrentPlayback) {
          this.currentPlaybackSettler = null;
        }
        if (audioService && this.currentAudioService === audioService) {
          this.currentAudioService = null;
        }
        item.onPlaybackEnd?.();
        complete();
      };
      resolveCurrentPlayback = () => {
        settle(() => resolve());
      };

      audioService = new MobileAudioService({
        volume: this.volume,
        onPlay: () => {
          item.onPlaybackStart?.();
        },
        onEnded: () => {
          settle(() => resolve());
        },
        onError: (error) => {
          settle(() => reject(error));
        },
      });

      this.currentAudioService = audioService;
      this.currentPlaybackSettler = resolveCurrentPlayback;

      audioService.playAudio(item.audioData)
        .then((result) => {
          if (!result.success) {
            settle(() => {
              reject(result.error || new AudioError(AudioErrorType.PLAYBACK_FAILED, 'Audio playback failed'));
            });
          }
        })
        .catch((error) => {
          settle(() => reject(error));
        });
    });
  }

  /**
   * Skip the current audio and play next
   */
  skip(): void {
    if (this.currentAudioService || this.currentPlaybackSettler) {
      this.isSkipping = true;
      const audioService = this.currentAudioService;
      const settleCurrentPlayback = this.currentPlaybackSettler;
      this.currentAudioService = null;
      this.currentPlaybackSettler = null;
      audioService?.stop();
      settleCurrentPlayback?.();
      this.isPlaying = false; // Set isPlaying to false immediately
      
      // Trigger next playback safely using setTimeout to avoid race conditions
      setTimeout(() => {
        this.isSkipping = false;
        if (!this.isPlaying) {
          this.playNext();
        }
      }, 0);
    }
  }

  /**
   * Pause current playback
   */
  pause(): void {
    if (this.currentAudioService) {
      // Web Audio API doesn't support pause/resume, so we stop the current audio
      this.currentAudioService = null;
    }
  }

  /**
   * Resume current playback
   */
  resume(): void {
    // Web Audio API doesn't support pause/resume
    // If needed, we would need to restart from the beginning
    if (!this.isPlaying && this.queue.length > 0) {
      this.playNext();
    }
  }

  /**
   * Get current playing status
   */
  getStatus(): {
    isPlaying: boolean;
    queueSize: number;
    currentItem?: AudioQueueItem;
  } {
    return {
      isPlaying: this.isPlaying,
      queueSize: this.queue.length,
      currentItem: this.queue[0]
    };
  }
}

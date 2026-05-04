/**
 * Audio Interaction Manager
 * Handles user interaction requirements for audio playback on mobile devices
 */

import { GlobalAudioManager } from './web-audio-player';
import {
  hasAudioUserInteraction,
  markAudioUserInteraction,
  registerAudioInteractionCallback,
  resetAudioUserInteractionGate
} from './audio-user-interaction-gate';
import { dispatchAudioInteractionRequired } from './audio-interaction-events';

type AudioContextSuspensionListener = (state: AudioContextState) => void;

const audioContextSuspensionListeners = new Set<AudioContextSuspensionListener>();

const isSuspendedAudioContextState = (state: AudioContextState): boolean =>
  state === 'suspended' || (state as string) === 'interrupted';

const notifyAudioContextSuspensionListeners = (state: AudioContextState): void => {
  audioContextSuspensionListeners.forEach((listener) => {
    try {
      listener(state);
    } catch (error) {
      console.error('[AudioInteractionManager] AudioContext suspension listener failed:', error);
    }
  });
};

export function registerAudioContextSuspensionListener(
  listener: AudioContextSuspensionListener,
): () => void {
  audioContextSuspensionListeners.add(listener);
  return () => {
    audioContextSuspensionListeners.delete(listener);
  };
}

export interface AudioInteractionEvents {
  onContextInitialized?: () => void;
  onInteractionRequired?: () => void;
  onError?: (error: Error) => void;
}

export interface UserInteractionPromptOptions {
  message?: string;
  buttonText?: string;
  timeout?: number;
  autoShow?: boolean;
}

export class AudioInteractionManager {
  private static instance: AudioInteractionManager;
  private globalAudioManager: GlobalAudioManager;
  private isContextInitialized = false;
  private initializationPromise: Promise<void> | null = null;
  private pendingInteractionCallbacks: (() => void)[] = [];
  private interactionEventListeners: AudioInteractionEvents = {};
  private hasUserInteracted = false;
  private interactionPromptElement: HTMLElement | null = null;
  private isPromptVisible = false;

  private constructor() {
    this.globalAudioManager = GlobalAudioManager.getInstance();
    this.hasUserInteracted = hasAudioUserInteraction();
    this.setupInteractionListeners();
  }

  public static getInstance(): AudioInteractionManager {
    if (typeof window === 'undefined') {
      throw new Error('AudioInteractionManager is not available during SSR');
    }

    if (!AudioInteractionManager.instance) {
      AudioInteractionManager.instance = new AudioInteractionManager();
    }
    return AudioInteractionManager.instance;
  }

  private runCallbackSafely(callback: () => void): void {
    try {
      callback();
    } catch (error) {
      console.error('Error executing pending audio callback:', error);
    }
  }

  private enqueuePendingInteractionCallback(callback: () => void): void {
    if (this.isContextInitialized) {
      this.runCallbackSafely(callback);
      return;
    }

    this.pendingInteractionCallbacks.push(callback);
  }

  private flushPendingInteractionCallbacks(): void {
    const callbacks = [...this.pendingInteractionCallbacks];
    this.pendingInteractionCallbacks = [];

    callbacks.forEach((callback) => {
      this.runCallbackSafely(callback);
    });
  }

  /**
   * Setup interaction event listeners
   */
  private setupInteractionListeners(): void {
    registerAudioInteractionCallback(async () => {
      this.hasUserInteracted = true;
      this.hideInteractionPrompt();

      try {
        await this.initializeAudioContext();
      } catch (error) {
        console.error('Failed to initialize audio context on user interaction:', error);
        this.interactionEventListeners.onError?.(error as Error);
      }
    });
  }

  /**
   * Initialize AudioContext after user interaction
   */
  private async initializeAudioContext(): Promise<void> {
    if (this.isContextInitialized) {
      await this.globalAudioManager.ensureResumed();
      this.flushPendingInteractionCallbacks();
      return;
    }

    if (!this.initializationPromise) {
      this.initializationPromise = (async () => {
        try {
          await this.globalAudioManager.initialize();
          this.isContextInitialized = true;
          this.flushPendingInteractionCallbacks();

          this.interactionEventListeners.onContextInitialized?.();
        } catch (error) {
          console.error('Failed to initialize AudioContext:', error);
          this.interactionEventListeners.onError?.(error as Error);
          throw error;
        } finally {
          this.initializationPromise = null;
        }
      })();
    }

    await this.initializationPromise;
  }

  /**
   * Ensure audio context is ready for playback
   */
  public async ensureAudioContext(): Promise<AudioContext> {
    if (this.isContextInitialized) {
      await this.globalAudioManager.ensureResumed();
      const context = this.globalAudioManager.getContext()!;
      if (hasAudioUserInteraction() && isSuspendedAudioContextState(context.state)) {
        notifyAudioContextSuspensionListeners(context.state);
      }
      return context;
    }

    this.hasUserInteracted = this.hasUserInteracted || hasAudioUserInteraction();
    if (!this.hasUserInteracted) {
      this.interactionEventListeners.onInteractionRequired?.();
      dispatchAudioInteractionRequired({
        reason: 'playback-blocked',
        message: 'User interaction required for audio playback',
        audioContextState: this.getAudioContextState(),
      });
      throw new Error('User interaction required for audio playback');
    }

    await this.initializeAudioContext();
    const context = this.globalAudioManager.getContext()!;
    if (hasAudioUserInteraction() && isSuspendedAudioContextState(context.state)) {
      notifyAudioContextSuspensionListeners(context.state);
    }
    return context;
  }

  /**
   * Show interaction prompt to user
   */
  private showInteractionPrompt(options: UserInteractionPromptOptions = {}): void {
    if (this.isPromptVisible || this.hasUserInteracted) return;

    const {
      message = 'タップして音声を有効化 / Tap to enable audio',
      buttonText = '🔊 音声ON / Enable Audio',
      timeout = 0
    } = options;

    // Create prompt element
    this.interactionPromptElement = document.createElement('div');
    this.interactionPromptElement.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: rgba(0, 0, 0, 0.9);
      color: white;
      padding: 20px;
      border-radius: 12px;
      text-align: center;
      z-index: 10000;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      max-width: 300px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      backdrop-filter: blur(10px);
    `;

    const messageElement = document.createElement('div');
    messageElement.style.cssText = 'margin-bottom: 16px; font-size: 14px; line-height: 1.4;';
    messageElement.textContent = message;

    const button = document.createElement('button');
    button.style.cssText = `
      background: #4CAF50;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 16px;
      cursor: pointer;
      transition: background 0.2s;
    `;
    button.textContent = buttonText;

    this.interactionPromptElement.append(messageElement, button);

    document.body.appendChild(this.interactionPromptElement);
    this.isPromptVisible = true;

    // Add click handler to unlock audio
    button.addEventListener('click', () => {
      markAudioUserInteraction();
    });

    // Auto-hide after timeout
    if (timeout > 0) {
      setTimeout(() => {
        this.hideInteractionPrompt();
      }, timeout);
    }
  }

  /**
   * Hide interaction prompt
   */
  private hideInteractionPrompt(): void {
    if (this.interactionPromptElement && this.isPromptVisible) {
      document.body.removeChild(this.interactionPromptElement);
      this.interactionPromptElement = null;
      this.isPromptVisible = false;
    }
  }

  /**
   * Request user interaction for audio playback
   */
  public async requestUserInteraction(options: UserInteractionPromptOptions = {}): Promise<AudioContext> {
    return new Promise((resolve, reject) => {
      this.hasUserInteracted = this.hasUserInteracted || hasAudioUserInteraction();
      if (this.isContextInitialized) {
        this.globalAudioManager.ensureResumed().then(() => {
          resolve(this.globalAudioManager.getContext()!);
        }).catch(reject);
        return;
      }

      if (this.hasUserInteracted) {
        this.initializeAudioContext().then(() => {
          const context = this.globalAudioManager.getContext();
          if (context) {
            resolve(context);
          } else {
            reject(new Error('Failed to get AudioContext'));
          }
        }).catch(reject);
        return;
      }

      // Show prompt to user
      this.showInteractionPrompt(options);

      // Add to pending callbacks
      this.enqueuePendingInteractionCallback(() => {
        const context = this.globalAudioManager.getContext();
        if (context) {
          resolve(context);
        } else {
          reject(new Error('Failed to get AudioContext'));
        }
      });

      // Notify that interaction is required
      this.interactionEventListeners.onInteractionRequired?.();
    });
  }

  /**
   * Execute callback when audio context is ready
   */
  public executeWhenReady(callback: () => void): void {
    this.hasUserInteracted = this.hasUserInteracted || hasAudioUserInteraction();
    if (this.isContextInitialized) {
      this.runCallbackSafely(callback);
      return;
    }

    this.enqueuePendingInteractionCallback(callback);

    if (this.hasUserInteracted) {
      this.initializeAudioContext().catch((error) => {
        console.error('Failed to initialize AudioContext for pending callback:', error);
        this.interactionEventListeners.onError?.(error as Error);
      });
      return;
    }

    this.interactionEventListeners.onInteractionRequired?.();
  }

  /**
   * Check if audio context is ready
   */
  public isAudioContextReady(): boolean {
    return this.isContextInitialized && this.globalAudioManager.isContextInitialized();
  }

  /**
   * Check if user has interacted
   */
  public hasUserInteraction(): boolean {
    this.hasUserInteracted = this.hasUserInteracted || hasAudioUserInteraction();
    return this.hasUserInteracted;
  }

  /**
   * Get AudioContext state
   */
  public getAudioContextState(): AudioContextState | null {
    const context = this.globalAudioManager.getContext();
    return context?.state || null;
  }

  /**
   * Set event listeners
   */
  public setEventListeners(listeners: AudioInteractionEvents): void {
    this.interactionEventListeners = { ...this.interactionEventListeners, ...listeners };
  }

  /**
   * Force initialize context (use with caution)
   */
  public async forceInitialize(): Promise<AudioContext> {
    markAudioUserInteraction();
    this.hasUserInteracted = true;
    this.unlockFromUserGesture();
    await this.initializeAudioContext();
    return this.globalAudioManager.getContext()!;
  }

  public unlockFromUserGesture(): AudioContext {
    markAudioUserInteraction();
    this.hasUserInteracted = true;
    return this.globalAudioManager.initializeFromUserGesture();
  }

  /**
   * Reset interaction state (for testing)
   */
  public reset(): void {
    this.hasUserInteracted = false;
    this.isContextInitialized = false;
    this.initializationPromise = null;
    this.pendingInteractionCallbacks = [];
    resetAudioUserInteractionGate();
    this.globalAudioManager.dispose();
  }

  /**
   * Dispose resources
   */
  public dispose(): void {
    this.globalAudioManager.dispose();
    this.initializationPromise = null;
    this.pendingInteractionCallbacks = [];
    this.interactionEventListeners = {};
  }
}

/**
 * Hook for React components to handle audio interaction
 */
export const useAudioInteraction = () => {
  const manager = AudioInteractionManager.getInstance();

  const ensureAudioContext = async (): Promise<AudioContext> => {
    return manager.ensureAudioContext();
  };

  const requestUserInteraction = async (): Promise<AudioContext> => {
    return manager.requestUserInteraction();
  };

  const executeWhenReady = (callback: () => void): void => {
    manager.executeWhenReady(callback);
  };

  const isReady = (): boolean => {
    return manager.isAudioContextReady();
  };

  const hasInteraction = (): boolean => {
    return manager.hasUserInteraction();
  };

  const getState = (): AudioContextState | null => {
    return manager.getAudioContextState();
  };

  return {
    ensureAudioContext,
    requestUserInteraction,
    executeWhenReady,
    isReady,
    hasInteraction,
    getState
  };
};

/**
 * Call directly from a trusted user gesture. Safari/iOS needs the actual
 * AudioContext creation/resume to start during that gesture, not after later
 * async STT/QA/TTS work.
 */
export const unlockAudioForUserGesture = (): void => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    markAudioUserInteraction();
    const manager = AudioInteractionManager.getInstance();
    manager.unlockFromUserGesture();
    void manager.forceInitialize().catch((error) => {
      console.warn('[AudioInteractionManager] Failed to unlock audio from user gesture:', error);
    });
  } catch (error) {
    console.warn('[AudioInteractionManager] Failed to start audio unlock:', error);
  }
};

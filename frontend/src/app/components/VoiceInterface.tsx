'use client';

import { AudioQueue } from '@/lib/audio-queue';
import { formatError } from '@/lib/error-messages';
import { MobileAudioService } from '@/lib/audio/mobile-audio-service';
import { useAudioInteraction } from '@/lib/audio/audio-interaction-manager';
import { VoiceRecorder } from '@/lib/voice-recorder';
import { audioStateManager } from '@/lib/audio-state-manager';
import { AlertCircle, Loader2, Mic, MicOff, Settings, Volume2, VolumeX } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useMicVAD, utils } from '@ricky0123/vad-react';

interface VoiceInterfaceProps {
  onLanguageChange?: (language: 'ja' | 'en') => void;
  layout?: 'vertical' | 'horizontal';
  language?: 'ja' | 'en';
  autoGreeting?: boolean;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
}

export default function VoiceInterface({ 
  onLanguageChange, 
  layout = 'vertical',
  language = 'ja',
  autoGreeting = false,
  onVisemeControl
}: VoiceInterfaceProps) {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [conversationState, setConversationState] = useState<'idle' | 'listening' | 'processing' | 'speaking'>('idle');
  const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>(language);
  const [volume, setVolumeState] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [autoListen, setAutoListen] = useState(true); // Auto-listen after response
  const [currentEmotion, setCurrentEmotion] = useState<string | null>(null);
  const [audioUnlocked, setAudioUnlocked] = useState(false);
  
  // Custom setVolume that also updates audio queue
  const setVolume = (newVolume: number) => {
    setVolumeState(newVolume);
    if (audioQueueRef.current) {
      audioQueueRef.current.setVolume(newVolume);
    }
  };
  

  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<AudioQueue | null>(null);
  const mobileAudioServiceRef = useRef<MobileAudioService | null>(null);
  const voiceRecorderRef = useRef<VoiceRecorder | null>(null);
  const initialVolumeRef = useRef(volume);
  const performAutoGreetingRef = useRef<() => Promise<void>>(async () => {});
  const { ensureAudioContext, isReady: isAudioReady, hasInteraction } = useAudioInteraction();

  // --- VAD barge-in integration ---
  // VAD is active only while AI is speaking (conversationState === 'speaking')
  const vadActiveRef = useRef(false);

  // Keep vadActiveRef in sync with conversationState
  useEffect(() => {
    vadActiveRef.current = conversationState === 'speaking';
  }, [conversationState]);

  // Stable callback for processing VAD-captured audio
  const processVadAudio = useCallback(async (audioBlob: Blob) => {
    await processAudioInput(audioBlob);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentLanguage, isMuted]);

  // Stable callback for VAD-triggered interruption
  const handleVadInterrupt = useCallback(() => {

    // 1. Stop AI audio playback
    if (mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current.stop();
    }
    audioStateManager.stopAll();
    if (audioQueueRef.current) {
      audioQueueRef.current.clear();
    }

    // 2. Stop lip-sync
    if (onVisemeControl) {
      onVisemeControl('X', 0);
    }

    // 3. Update UI state
    setIsSpeaking(false);
    setConversationState('listening');

    // 4. Notify backend of interruption (fire-and-forget)
    fetch('/api/voice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'handle_interruption' }),
    }).catch((err) => console.error('[VAD] Failed to notify backend of interruption:', err));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onVisemeControl]);

  const vadInstance = useMicVAD({
    // Kiosk-optimized thresholds
    positiveSpeechThreshold: 0.6,
    negativeSpeechThreshold: 0.45,
    minSpeechMs: 150,
    redemptionMs: 400,
    startOnLoad: true,

    onSpeechStart: () => {
      // Only act when AI is speaking
      if (!vadActiveRef.current) return;
      handleVadInterrupt();
    },

    onSpeechEnd: (audio: Float32Array) => {
      // Only process if we were in a barge-in scenario (now in 'listening' state after interrupt)
      // or if conversation is idle/listening (VAD detected real speech)
      if (vadActiveRef.current) {
        // Still speaking and speech ended quickly — treat as misfire, ignore
        return;
      }

      // Convert Float32Array to WAV Blob and send to existing STT pipeline
      const wavBuffer = utils.encodeWAV(audio);
      const audioBlob = new Blob([wavBuffer], { type: 'audio/wav' });

      // Only process if the blob has meaningful size (avoid empty/tiny misfires)
      if (audioBlob.size < 1000) {
        return;
      }

      setConversationState('processing');
      processVadAudio(audioBlob);
    },

    onVADMisfire: () => {
      // No action needed - if we already interrupted, audio is stopped and
      // we cannot resume it. The brief false positive is acceptable for kiosk UX.
    },
  });

  // Audio unlock function
  const unlockAudio = async () => {
    if (audioUnlocked) return;

    try {
      // Initialize AudioContext if it doesn't exist
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }

      // Resume AudioContext if suspended
      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }
      
      setAudioUnlocked(true);
    } catch (error) {
      console.warn('[AUDIO] Audio unlock failed:', error);
    }
  };

  // Initialize mobile audio service
  useEffect(() => {
    if (!mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current = new MobileAudioService({
        volume: initialVolumeRef.current,
        onPlay: () => setIsSpeaking(true),
        onEnded: () => setIsSpeaking(false),
        onError: (error) => {
          console.error('[AUDIO] Mobile audio service error:', error);
          setError(`Audio playback error: ${error.message}`);
        }
      });
    }

    const audioQueue = audioQueueRef.current;
    const audioContext = audioContextRef.current;
    const mobileAudioService = mobileAudioServiceRef.current;

    return () => {
      // Cleanup VoiceRecorder
      if (voiceRecorderRef.current) {
        voiceRecorderRef.current.cleanup();
        voiceRecorderRef.current = null;
      }
      
      if (audioContext) {
        audioContext.close();
      }
      if (audioQueue) {
        audioQueue.clear();
      }
      if (mobileAudioService) {
        mobileAudioService.dispose();
      }
    };
  }, []);

  // Update mobile audio service volume
  useEffect(() => {
    if (mobileAudioServiceRef.current) {
      mobileAudioServiceRef.current.setVolume(volume);
    }
  }, [volume]);

  // Update language when prop changes
  useEffect(() => {
    setCurrentLanguage(language);
  }, [language]);

  // Auto greeting when component mounts with autoGreeting enabled
  useEffect(() => {
    if (autoGreeting) {
      void performAutoGreetingRef.current();
    }
  }, [autoGreeting, language]);

  // Perform automatic greeting
  const performAutoGreeting = async () => {
    const greetingText = language === 'ja' 
      ? 'はじめまして！何かお手伝いできることはありますか？'
      : 'Hello there! How can I help you today?';
    
    try {
      // Wait a bit to ensure audio context can be initialized
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Ensure audio context is ready
      if (audioContextRef.current?.state === 'suspended') {
      }
      
      setConversationState('speaking');
      setResponse(greetingText);
      setIsLoading(true);
      setLoadingMessage(language === 'ja' ? '挨拶を準備中...' : 'Preparing greeting...');

      // Generate TTS audio for greeting
      const response = await fetch('/api/voice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'text_to_speech',
          text: greetingText,
          language: language,
          sessionId: generateSessionId(),
        }),
      });

      const result = await response.json();

      if (result.success && result.audioResponse && !isMuted) {
        await playAudioResponse(result.audioResponse);
      } else {
        setConversationState('idle');
        setIsLoading(false);
        setLoadingMessage('');
      }

      // Update character animation for greeting
      updateCharacter('greeting');

    } catch (error) {
      console.error('Auto greeting error:', error);
      setError(language === 'ja' ? '挨拶の再生に失敗しました' : 'Failed to play greeting');
      setConversationState('idle');
      setIsLoading(false);
      setLoadingMessage('');
    }
  };

  performAutoGreetingRef.current = performAutoGreeting;


  // Start voice recording
  const startListening = async () => {
    try {
      setError(null);
      
      // Stop any currently playing audio to prevent overlap
      audioStateManager.stopAll();
      
      // Also stop local audio queue if it exists
      if (audioQueueRef.current && audioQueueRef.current.clear) {
        audioQueueRef.current.clear();
      }
      
      // Initialize and unlock audio for iOS - this is critical!
      
      // Ensure audio context is initialized and running
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      
      if (audioContextRef.current?.state === 'suspended') {
        await audioContextRef.current.resume();
      }
      
      // Ensure iOS audio is unlocked
      await unlockAudio();
      
      // Import VoiceRecorder
      const { VoiceRecorder } = await import('@/lib/voice-recorder');
      
      setIsLoading(true);
      setLoadingMessage(currentLanguage === 'ja' ? 'マイクにアクセス中...' : 'Accessing microphone...');
      
      // Create and initialize VoiceRecorder instance
      const recorder = new VoiceRecorder(
        (audioBlob: Blob) => {
          // onDataAvailable callback
          processAudioInput(audioBlob);
        },
        (error: Error) => {
          // onError callback
          console.error('VoiceRecorder error:', error);
          setError(error.message);
          setIsLoading(false);
          setLoadingMessage('');
          setIsRecording(false);
          setIsListening(false);
          setConversationState('idle');
        }
      );
      
      // Initialize the recorder (handles iOS-specific requirements)
      await recorder.initialize();
      
      // Check if initialization was successful
      if (!recorder.isInitialized()) {
        // Error already handled by onError callback
        return;
      }
      
      // Store recorder reference in component ref
      voiceRecorderRef.current = recorder;
      
      // Start recording
      recorder.start();
      
      setIsRecording(true);
      setIsListening(true);
      setConversationState('listening');
      setIsLoading(false);
      setLoadingMessage('');
    } catch (error: any) {
      console.error('Error starting voice recording:', error);
      setError(formatError(error, currentLanguage));
      setIsLoading(false);
      setLoadingMessage('');
    }
  };

  // Stop voice recording
  const stopListening = () => {
    // Stop any currently playing audio
    audioStateManager.stopAll();
    
    // Also stop local audio queue if it exists
    if (audioQueueRef.current && audioQueueRef.current.clear) {
      audioQueueRef.current.clear();
    }
    
    if (isRecording && voiceRecorderRef.current) {
      const recorder = voiceRecorderRef.current;
      recorder.stop();
      // Cleanup immediately, no setTimeout needed
      recorder.cleanup();
      voiceRecorderRef.current = null;
      
      setIsRecording(false);
      setIsListening(false);
      setConversationState('processing');
    }
  };

  // Process audio input
  const processAudioInput = async (audioBlob: Blob) => {
    try {
      setIsLoading(true);
      setLoadingMessage(currentLanguage === 'ja' ? '音声を認識中...' : 'Recognizing speech...');
      const audioBuffer = await audioBlob.arrayBuffer();
      const uint8Array = new Uint8Array(audioBuffer);
      const audioBase64 = btoa(String.fromCharCode.apply(null, Array.from(uint8Array)));

      const response = await fetch('/api/voice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'process_voice',
          audioData: audioBase64,
          sessionId: generateSessionId(),
          language: currentLanguage, // 重要：言語設定を明示的に指定
        }),
      });

      const result = await response.json();

      if (result.success) {
        setTranscript(result.transcript);
        setResponse(result.response);
        
        // Update loading message for TTS generation
        setLoadingMessage(currentLanguage === 'ja' ? '音声を生成中...' : 'Generating voice...');

        // Play audio response
        
        if (result.audioResponse && !isMuted) {
          try {
            await playAudioResponse(result.audioResponse);
          } catch (audioError) {
            console.error('[DEBUG] Audio playback failed:', audioError);
            // Fallback: show manual play button
            setError(currentLanguage === 'ja' 
              ? '🔊 音声再生に失敗しました。下のボタンをタップして再生してください。' 
              : '🔊 Audio playback failed. Tap the button below to play.');
            setConversationState('idle');
            setIsLoading(false);
            setLoadingMessage('');
          }
        } else {
          setConversationState('idle');
          setIsLoading(false);
          setLoadingMessage('');
        }

        // Update character if needed
        if (result.shouldUpdateCharacter) {
          if (result.characterAction) {
            updateCharacter(result.characterAction);
          }
          // Update character expression based on emotion
          if (result.emotion || result.primaryEmotion) {
            const emotion = result.primaryEmotion || result.emotion?.emotion || 'neutral';
            setCurrentEmotion(emotion);
            updateCharacterExpression(emotion);
          }
        }
      } else {
        setError(result.error || formatError({ code: 'VOICE_PROCESSING_ERROR' }, currentLanguage));
      }
    } catch (error: any) {
      console.error('Error processing audio:', error);
      setError(formatError(error, currentLanguage));
    } finally {
      setConversationState('idle');
      setIsLoading(false);
      setLoadingMessage('');
    }
  };

  // Play streaming audio response

  // Play audio response
  const playAudioResponse = async (audioBase64: string) => {
    try {
      
      
      // Attempt audio unlock for mobile devices
      try {
        await unlockAudio();
      } catch (error) {
        console.warn('[AUDIO] Audio unlock failed, continuing with standard playback');
      }
      setIsLoading(true);
      setLoadingMessage(currentLanguage === 'ja' ? '音声を再生準備中...' : 'Preparing audio playback...');
      setIsSpeaking(true);
      setConversationState('speaking');

      // Stop any currently playing audio via mobile audio service
      if (mobileAudioServiceRef.current) {
        mobileAudioServiceRef.current.stop();
      }
      
      // Clean up audio queue if exists
      if (audioQueueRef.current) {
        audioQueueRef.current.clear();
      }

      const audioData = Uint8Array.from(atob(audioBase64), c => c.charCodeAt(0));
      const audioBlob = new Blob([audioData], { type: 'audio/mp3' });
      const audioUrl = URL.createObjectURL(audioBlob);
      
      
      // Ensure mobile audio service is available (should already be initialized by useEffect)
      if (!mobileAudioServiceRef.current) {
        console.error('[AUDIO] MobileAudioService not initialized');
        setError('Audio service not available');
        return;
      }

      // Import performance monitor functions
      const { measurePerformance } = await import('@/lib/performance-monitor');

      // Skip lip-sync for very large audio files to improve performance
      const skipLipSync = audioBlob.size > 500000;
      
      // Start lip-sync analysis in background (non-blocking)
      const lipSyncPromise = (async () => {
        if (skipLipSync) {
          return;
        }
        
        try {
          
          // Analyze audio for lip-sync
          const { LipSyncAnalyzer } = await import('@/lib/lip-sync-analyzer');
          const analyzer = new LipSyncAnalyzer();
          const lipSyncData = await measurePerformance(
            'Lip-sync analysis',
            () => analyzer.analyzeLipSync(audioBlob)
          );
          
          
          // Apply lip-sync to character using direct viseme callback
          if (onVisemeControl) {
            
            // Schedule viseme updates using direct callback
            let frameIndex = 0;
            const updateLipSync = () => {
              if (frameIndex < lipSyncData.frames.length && onVisemeControl) {
                const frame = lipSyncData.frames[frameIndex];
                
                
                // Use direct viseme callback instead of API
                onVisemeControl(frame.mouthShape, frame.mouthOpen);
                
                frameIndex++;
                setTimeout(updateLipSync, 100); // 10fps for better performance
              } else {
                // Reset to closed mouth
                if (onVisemeControl) {
                  onVisemeControl('X', 0);
                }
              }
            };
            
            // Start lip-sync animation immediately since we control playback timing
            updateLipSync();
          } else {
            console.warn('onVisemeControl callback not available - skipping lip-sync');
          }

          analyzer.dispose();
        } catch (lipSyncError) {
          console.warn('Lip-sync analysis failed, continuing with audio playback:', lipSyncError);
        }
      })();

      // Audio service should already be initialized by useEffect
      
      // Set up audio ended handler for this specific playback
      const handleAudioEnd = () => {
        setIsSpeaking(false);
        setConversationState('idle');
        setIsLoading(false);
        setLoadingMessage('');
        
        // Clean up audio resources
        if (mobileAudioServiceRef.current) {
          mobileAudioServiceRef.current.stop();
        }
        
        // Revoke object URL after a delay to ensure cleanup
        setTimeout(() => {
          URL.revokeObjectURL(audioUrl);
        }, 100);
        
        // Stop lip-sync with direct callback
        if (onVisemeControl) {
          onVisemeControl('X', 0);
        }
        
        // Restore emotion expression after lip-sync if needed
        if (currentEmotion && currentEmotion !== 'neutral') {
          setTimeout(() => {
            updateCharacterExpression(currentEmotion);
          }, 200);
        }
        
        // Auto-listen if enabled
        if (autoListen && !isMuted) {
          setTimeout(() => {
            startListening();
          }, 1000); // 1 second delay before auto-listening
        }
      };
      
      const handleAudioError = (error: Error) => {
        console.error('[AUDIO] Mobile audio service error:', error);
        setIsSpeaking(false);
        setConversationState('idle');
        setIsLoading(false);
        setLoadingMessage('');
        setError(formatError({ code: 'VOICE_PROCESSING_ERROR' }, currentLanguage));
        URL.revokeObjectURL(audioUrl);
        
        // Stop lip-sync on error with direct callback
        if (onVisemeControl) {
          onVisemeControl('X', 0);
        }
      };

      // Update event handlers for this specific playback
      mobileAudioServiceRef.current.updateEventHandlers({
        onPlay: () => setIsSpeaking(true),
        onEnded: handleAudioEnd,
        onError: handleAudioError
      });

      // Set loading state to false before playing audio (UI becomes responsive)
      setIsLoading(false);
      setLoadingMessage('');
      
      try {
        const isTablet = /iPad|Android.*Tablet/i.test(navigator.userAgent);

        // Use mobile audio service for better compatibility
        const result = await mobileAudioServiceRef.current!.playAudio(audioUrl);
        
        
        if (result.success) {
          
          // Skip lip-sync processing entirely on iOS
          if (!skipLipSync) {
            // Start lip-sync processing in background (non-blocking)
            lipSyncPromise.catch(error => {
              console.warn('Lip-sync processing error (non-critical):', error);
            });
          }
        } else {
          console.error('[AUDIO] Audio playback failed:', {
            error: result.error,
            method: result.method,
            requiresInteraction: result.error?.requiresUserInteraction || false,
            isTablet
          });
          throw result.error || new Error('Audio playback failed');
        }
      } catch (playError: any) {
        console.error('Audio playback failed:', playError);
        
        // If interaction is required, show a message and retry on next user interaction
        if (playError.message?.includes('User interaction required') || playError.name === 'NotAllowedError') {
          
          // Create a one-time click handler to retry playback
          const retryPlayback = async () => {
            try {
              // Ensure audio context and retry playback
              await ensureAudioContext();
              
              const retryResult = await mobileAudioServiceRef.current!.playAudio(audioUrl);
              if (retryResult.success) {
                
                // Clear the error message
                setError(null);
                
                // Skip lip-sync processing entirely on iOS
                if (!skipLipSync) {
                  lipSyncPromise.catch(error => {
                    console.warn('Lip-sync processing error (non-critical):', error);
                  });
                }
              } else {
                throw retryResult.error || new Error('Retry playback failed');
              }
              
            } catch (retryError) {
              console.error('[AUDIO] Retry playback failed:', retryError);
              setError(currentLanguage === 'ja' 
                ? '音声再生に失敗しました。ページを更新してください。' 
                : 'Audio playback failed. Please refresh the page.');
            }
            
            // Remove event listeners
            document.removeEventListener('click', retryPlayback);
            document.removeEventListener('touchstart', retryPlayback);
            document.removeEventListener('keydown', retryPlayback);
          };
          
          // Add multiple event listeners for user interaction
          document.addEventListener('click', retryPlayback, { once: true });
          document.addEventListener('touchstart', retryPlayback, { once: true });
          document.addEventListener('keydown', retryPlayback, { once: true });
          
          // Update UI to show user needs to interact
          setError(currentLanguage === 'ja' 
            ? '🔊 音声を再生するには画面をタップしてください' 
            : '🔊 Tap anywhere to play audio');
          
          // Don't throw the error, just wait for user interaction
          return;
        } else {
          throw playError;
        }
      }
    } catch (error: any) {
      console.error('[AUDIO] Error playing audio:', error);
      setIsSpeaking(false);
      setConversationState('idle');
      setIsLoading(false);
      setLoadingMessage('');
      setError(formatError(error, currentLanguage));
    }
  };

  // Update character animation
  const updateCharacter = async (action: string) => {
    try {
      await fetch('/api/character', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'playAnimation',
          animation: action,
          transition: true,
        }),
      });
    } catch (error) {
      console.error('Error updating character:', error);
    }
  };
  
  // Update character expression
  const updateCharacterExpression = async (expression: string) => {
    try {
      const response = await fetch('/api/character', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'setExpression',
          expression: expression,
          transition: true,
        }),
      });
      const result = await response.json();
    } catch (error) {
      console.error('Error updating character expression:', error);
    }
  };

  // Generate session ID
  const generateSessionId = () => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  // Handle interruption
  const handleInterruption = async () => {
    if (isSpeaking) {
      // Stop current audio via mobile audio service
      if (mobileAudioServiceRef.current) {
        mobileAudioServiceRef.current.stop();
      }
      
      // Stop audio queue if streaming
      if (audioQueueRef.current) {
        audioQueueRef.current.clear();
      }

      // Notify backend of interruption
      try {
        await fetch('/api/voice', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'handle_interruption',
          }),
        });
      } catch (error) {
        console.error('Error handling interruption:', error);
      }

      setIsSpeaking(false);
      setConversationState('idle');
    }
  };

  // Toggle language
  const toggleLanguage = async () => {
    const newLanguage = currentLanguage === 'ja' ? 'en' : 'ja';
    
    try {
      setIsLoading(true);
      setLoadingMessage(currentLanguage === 'ja' ? '言語を切り替え中...' : 'Switching language...');
      const response = await fetch('/api/voice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'set_language',
          language: newLanguage,
        }),
      });

      const result = await response.json();
      
      if (result.success) {
        setCurrentLanguage(newLanguage);
        onLanguageChange?.(newLanguage);
      }
    } catch (error: any) {
      console.error('Error changing language:', error);
      setError(formatError(error, currentLanguage));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  };

  // Clear conversation
  const clearConversation = async () => {
    try {
      await fetch('/api/voice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action: 'clear_conversation',
        }),
      });

      setTranscript('');
      setResponse('');
      setError(null);
    } catch (error) {
      console.error('Error clearing conversation:', error);
    }
  };

  if (layout === 'horizontal') {
    return (
      <div className="glass rounded-2xl p-4 shadow-2xl border border-white/30">
        
        <div className="flex items-center gap-6">
          {/* Status Indicator */}
          <div className="flex items-center space-x-3">
            {isLoading ? (
              <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
            ) : (
              <div className={`w-3 h-3 rounded-full transition-all duration-500 ${
                conversationState === 'idle' ? 'bg-gray-400' :
                conversationState === 'listening' ? 'bg-blue-500 animate-pulse' :
                conversationState === 'processing' ? 'bg-yellow-500 animate-bounce' :
                'bg-green-500 animate-pulse'
              }`} />
            )}
            <span className="text-base md:text-lg font-medium text-gray-700 whitespace-nowrap">
              {isLoading && loadingMessage ? loadingMessage :
                conversationState === 'idle' && (currentLanguage === 'ja' ? '待機中' : 'Ready') ||
                conversationState === 'listening' && (currentLanguage === 'ja' ? '聞いています...' : 'Listening...') ||
                conversationState === 'processing' && (currentLanguage === 'ja' ? '処理中...' : 'Processing...') ||
                conversationState === 'speaking' && (currentLanguage === 'ja' ? '話しています...' : 'Speaking...')
              }
            </span>
          </div>

          {/* Voice Waveform Indicator */}
          {(isListening || isSpeaking) && (
            <div className="flex items-center space-x-1 h-6">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="voice-wave-bar w-1 bg-primary rounded-full transition-all"
                  style={{ height: '100%' }}
                />
              ))}
            </div>
          )}

          {/* Main Controls */}
          <div className="flex items-center space-x-3">
            {/* Voice button */}
            <button
              onClick={isListening ? stopListening : startListening}
              disabled={conversationState === 'processing' || isLoading}
              className={`p-5 md:p-6 rounded-full transition-smooth transform ${
                isListening 
                  ? 'bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white shadow-lg scale-110 ring-4 ring-red-500/30' 
                  : (conversationState === 'processing' || isLoading)
                  ? 'bg-gray-400 text-white cursor-not-allowed'
                  : 'bg-gradient-to-r from-primary to-secondary hover:from-secondary hover:to-primary text-white shadow-lg hover:shadow-xl hover:scale-105'
              }`}
              title={isLoading && loadingMessage ? loadingMessage : 
                     isListening ? (currentLanguage === 'ja' ? '停止' : 'Stop') : 
                     (currentLanguage === 'ja' ? '録音開始' : 'Start recording')}
            >
              {isLoading && !isListening ? (
                <Loader2 className="w-7 h-7 md:w-8 md:h-8 animate-spin" />
              ) : isListening ? (
                <MicOff className="w-7 h-7 md:w-8 md:h-8" />
              ) : (
                <Mic className="w-7 h-7 md:w-8 md:h-8" />
              )}
            </button>

            {/* Interruption button */}
            {isSpeaking && (
              <button
                onClick={handleInterruption}
                className="p-4 md:p-5 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white shadow-lg transition-smooth transform hover:scale-105 touch-manipulation"
                title={currentLanguage === 'ja' ? '話を止める' : 'Interrupt'}
              >
                <VolumeX className="w-6 h-6 md:w-7 md:h-7" />
              </button>
            )}

            {/* Volume control */}
            <button
              onClick={() => setIsMuted(!isMuted)}
              className={`p-4 md:p-5 rounded-full transition-smooth transform hover:scale-105 touch-manipulation ${
                isMuted 
                  ? 'bg-gray-500 hover:bg-gray-600' 
                  : 'bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700'
              } text-white shadow-lg`}
            >
              {isMuted ? (
                <VolumeX className="w-6 h-6 md:w-7 md:h-7" />
              ) : (
                <Volume2 className="w-6 h-6 md:w-7 md:h-7" />
              )}
            </button>
          </div>

          {/* Volume Slider */}
          {!isMuted && (
            <div className="flex items-center space-x-3 flex-1 max-w-xs">
              <label className="text-sm md:text-base text-gray-600 whitespace-nowrap">
                {currentLanguage === 'ja' ? '音量' : 'Volume'}
              </label>
              <div className="slider-container flex-1">
                <div 
                  className="slider-fill" 
                  style={{ width: `${volume * 100}%` }}
                />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={volume}
                  onChange={(e) => setVolume(parseFloat(e.target.value))}
                  className="slider w-full"
                />
              </div>
              <span className="text-sm md:text-base text-gray-500 whitespace-nowrap">
                {Math.round(volume * 100)}%
              </span>
            </div>
          )}

          {/* Conversation Display (Compact) */}
          {(transcript || response) && (
            <div className="flex-1 max-w-lg">
              <div className="bg-gray-50/50 backdrop-blur-sm rounded-lg px-4 py-2 max-h-12 overflow-hidden">
                {response ? (
                  <p className="text-sm text-gray-800 truncate">
                    <span className="text-xs text-secondary font-semibold">AI: </span>
                    {response}
                  </p>
                ) : transcript && (
                  <p className="text-sm text-gray-800 truncate">
                    <span className="text-xs text-primary font-semibold">
                      {currentLanguage === 'ja' ? 'あなた: ' : 'You: '}
                    </span>
                    {transcript}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center space-x-2">
            <div className="px-2 py-1 bg-primary/10 rounded-full">
              <span className="text-xs font-semibold text-primary">
                {currentLanguage.toUpperCase()}
              </span>
            </div>
            
            <button
              onClick={toggleLanguage}
              className="btn-primary text-sm px-3 py-1.5"
            >
              {currentLanguage === 'ja' ? 'EN' : 'JP'}
            </button>
            
            <button
              onClick={clearConversation}
              className="btn-secondary text-sm px-3 py-1.5"
            >
              {currentLanguage === 'ja' ? 'リセット' : 'Clear'}
            </button>
            
            <button
              className="p-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-smooth"
              title={currentLanguage === 'ja' ? '設定' : 'Settings'}
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mt-3 bg-red-50/80 border border-red-200 rounded-lg px-3 py-2 backdrop-blur-sm flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-800">{error}</p>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-500 hover:text-red-700 transition-colors"
              aria-label={currentLanguage === 'ja' ? 'エラーを閉じる' : 'Close error'}
            >
              ×
            </button>
          </div>
        )}
      </div>
    );
  }

  // Original vertical layout
  return (
    <div className="glass rounded-2xl p-6 max-w-md shadow-2xl border border-white/30">
      
      {/* Status Indicator */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          {isLoading ? (
            <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
          ) : (
            <div className={`w-3 h-3 rounded-full transition-all duration-500 ${
              conversationState === 'idle' ? 'bg-gray-400' :
              conversationState === 'listening' ? 'bg-blue-500 animate-pulse' :
              conversationState === 'processing' ? 'bg-yellow-500 animate-bounce' :
              'bg-green-500 animate-pulse'
            }`} />
          )}
          <span className="text-base md:text-lg font-medium text-gray-700">
            {isLoading && loadingMessage ? loadingMessage :
              conversationState === 'idle' && (currentLanguage === 'ja' ? '待機中' : 'Ready') ||
              conversationState === 'listening' && (currentLanguage === 'ja' ? '聞いています...' : 'Listening...') ||
              conversationState === 'processing' && (currentLanguage === 'ja' ? '処理中...' : 'Processing...') ||
              conversationState === 'speaking' && (currentLanguage === 'ja' ? '話しています...' : 'Speaking...')
            }
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="px-2 py-1 bg-primary/10 rounded-full">
            <span className="text-xs font-semibold text-primary">
              {currentLanguage.toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Voice Waveform Indicator */}
      {(isListening || isSpeaking) && (
        <div className="flex items-center justify-center space-x-1 mb-4 h-8">
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="voice-wave-bar w-1 bg-primary rounded-full transition-all"
              style={{ height: '100%' }}
            />
          ))}
        </div>
      )}

      {/* Main Controls */}
      <div className="flex items-center justify-center space-x-4 mb-4">
        {/* Voice button */}
        <button
          onClick={isListening ? stopListening : startListening}
          disabled={conversationState === 'processing' || isLoading}
          className={`p-6 md:p-8 rounded-full transition-smooth transform ${
            isListening 
              ? 'bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white shadow-lg scale-110 ring-4 ring-red-500/30' 
              : (conversationState === 'processing' || isLoading)
              ? 'bg-gray-400 text-white cursor-not-allowed'
              : 'bg-gradient-to-r from-primary to-secondary hover:from-secondary hover:to-primary text-white shadow-lg hover:shadow-xl hover:scale-105'
          }`}
          title={isLoading && loadingMessage ? loadingMessage : 
                 isListening ? (currentLanguage === 'ja' ? '停止' : 'Stop') : 
                 (currentLanguage === 'ja' ? '録音開始' : 'Start recording')}
        >
          {isLoading && !isListening ? (
            <Loader2 className="w-8 h-8 md:w-10 md:h-10 animate-spin" />
          ) : isListening ? (
            <MicOff className="w-8 h-8 md:w-10 md:h-10" />
          ) : (
            <Mic className="w-8 h-8 md:w-10 md:h-10" />
          )}
        </button>

        {/* Interruption button */}
        {isSpeaking && (
          <button
            onClick={handleInterruption}
            className="p-5 md:p-6 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white shadow-lg transition-smooth transform hover:scale-105 touch-manipulation"
            title={currentLanguage === 'ja' ? '話を止める' : 'Interrupt'}
          >
            <VolumeX className="w-7 h-7 md:w-8 md:h-8" />
          </button>
        )}

        {/* Volume control */}
        <button
          onClick={() => setIsMuted(!isMuted)}
          className={`p-5 md:p-6 rounded-full transition-smooth transform hover:scale-105 touch-manipulation ${
            isMuted 
              ? 'bg-gray-500 hover:bg-gray-600' 
              : 'bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700'
          } text-white shadow-lg`}
        >
          {isMuted ? (
            <VolumeX className="w-7 h-7 md:w-8 md:h-8" />
          ) : (
            <Volume2 className="w-7 h-7 md:w-8 md:h-8" />
          )}
        </button>
      </div>

      {/* Volume Slider */}
      {!isMuted && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm md:text-base text-gray-600">
              {currentLanguage === 'ja' ? '音量' : 'Volume'}
            </label>
            <span className="text-sm md:text-base text-gray-500">
              {Math.round(volume * 100)}%
            </span>
          </div>
          <div className="slider-container">
            <div 
              className="slider-fill" 
              style={{ width: `${volume * 100}%` }}
            />
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={volume}
              onChange={(e) => setVolume(parseFloat(e.target.value))}
              className="slider"
            />
          </div>
        </div>
      )}

      {/* Conversation Display */}
      {(transcript || response) && (
        <div className="bg-gray-50/50 backdrop-blur-sm rounded-lg p-3 mb-4 max-h-40 overflow-y-auto scrollbar-thin">
          {transcript && (
            <div className="mb-2">
              <span className="text-xs text-primary font-semibold">
                {currentLanguage === 'ja' ? 'あなた:' : 'You:'}
              </span>
              <p className="text-sm text-gray-800 mt-1">
                {transcript}
              </p>
            </div>
          )}
          {response && (
            <div>
              <span className="text-xs text-secondary font-semibold">
                {currentLanguage === 'ja' ? 'AI:' : 'AI:'}
              </span>
              <p className="text-sm text-gray-800 mt-1">{response}</p>
            </div>
          )}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50/80 border border-red-200 rounded-lg p-3 mb-4 backdrop-blur-sm">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-800 flex-1">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-red-500 hover:text-red-700 transition-colors text-lg leading-none"
              aria-label={currentLanguage === 'ja' ? 'エラーを閉じる' : 'Close error'}
            >
              ×
            </button>
          </div>
        </div>
      )}


      {/* Action Buttons */}
      <div className="flex flex-col gap-2">
        {/* Main actions */}
        <div className="flex space-x-2">
          <button
            onClick={toggleLanguage}
            className="btn-primary flex-1 py-4 md:py-5 text-base md:text-lg touch-manipulation"
          >
            {currentLanguage === 'ja' ? 'English' : '日本語'}
          </button>
          
          <button
            onClick={clearConversation}
            className="btn-secondary flex-1 py-4 md:py-5 text-base md:text-lg touch-manipulation"
          >
            {currentLanguage === 'ja' ? 'リセット' : 'Clear'}
          </button>
          
          <button
            className="p-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-smooth"
            title={currentLanguage === 'ja' ? '設定' : 'Settings'}
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
        
        {/* Auto-listen toggle */}
        <div className="flex items-center justify-center space-x-2">
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={autoListen}
              onChange={(e) => setAutoListen(e.target.checked)}
              className="sr-only"
            />
            <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              autoListen ? 'bg-primary' : 'bg-gray-300'
            }`}>
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                autoListen ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </div>
            <span className="ml-2 text-base md:text-lg text-gray-700">
              {currentLanguage === 'ja' ? '自動リスニング' : 'Auto-listen'}
            </span>
          </label>
        </div>
      </div>

      {/* Instructions */}
      <div className="mt-4 text-center">
        <p className="text-sm md:text-base text-gray-500">
          {currentLanguage === 'ja' 
            ? 'マイクボタンを押して話しかけてください' 
            : 'Press the mic button to start talking'
          }
        </p>
      </div>
    </div>
  );
}

declare global {
  interface Window {
    __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string;
    __PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__?: string;
  }
}

interface VoiceRecorderOptions {
  getSessionId?: () => string;
  telemetryEndpoint?: string;
}

type DeviceIdMode = 'unset' | 'default' | 'custom';

export class VoiceRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  protected stream: MediaStream | null = null;
  private isRecording = false;
  private static readonly SELECTED_MIC_DEVICE_ID_STORAGE_KEY = 'kiosk-mic-device-id';

  constructor(
    private onDataAvailable: (audioBlob: Blob) => void,
    private onError: (error: Error) => void,
    private onHardwareReleased?: () => void,
    private options: VoiceRecorderOptions = {},
  ) {}

  private createRecorderError(message: string, source?: unknown): Error & { originalName?: string } {
    const originalName =
      source && typeof source === 'object' && 'name' in source
        ? String((source as { name?: unknown }).name ?? '')
        : '';
    const originalMessage =
      source && typeof source === 'object' && 'message' in source
        ? String((source as { message?: unknown }).message ?? '')
        : '';
    const error = new Error(originalMessage ? `${message}: ${originalMessage}` : message) as Error & {
      originalName?: string;
    };
    if (originalName) {
      error.name = originalName;
      error.originalName = originalName;
    }
    return error;
  }

  private resolveSessionId(): string | undefined {
    try {
      const sessionId = this.options.getSessionId?.();
      return typeof sessionId === 'string' && sessionId.length > 0 ? sessionId : undefined;
    } catch {
      return undefined;
    }
  }

  private getDeviceIdMode(selectedDeviceId: string | null | undefined): DeviceIdMode {
    if (!selectedDeviceId) {
      return 'unset';
    }
    return selectedDeviceId === 'default' ? 'default' : 'custom';
  }

  private getErrorName(source: unknown): string | undefined {
    if (source && typeof source === 'object' && 'name' in source) {
      const name = String((source as { name?: unknown }).name ?? '');
      return name || undefined;
    }
    return undefined;
  }

  private getErrorMessage(source: unknown): string | undefined {
    if (source && typeof source === 'object' && 'message' in source) {
      const message = String((source as { message?: unknown }).message ?? '');
      return message ? message.slice(0, 500) : undefined;
    }
    if (typeof source === 'string') {
      return source.slice(0, 500);
    }
    return undefined;
  }

  private reportClientTelemetry(
    phase: string,
    source?: unknown,
    extra: Record<string, unknown> = {},
  ): void {
    if (typeof window === 'undefined') {
      return;
    }

    const payload = {
      action: 'client_telemetry',
      event: 'voice_recorder_error',
      phase,
      sessionId: this.resolveSessionId(),
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
      errorName: this.getErrorName(source),
      errorMessage: this.getErrorMessage(source),
      timestamp: new Date().toISOString(),
      ...extra,
    };

    window.dispatchEvent(new CustomEvent('voice-recorder-telemetry', { detail: payload }));

    const endpoint = this.options.telemetryEndpoint ?? '/api/voice';
    window
      .fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        keepalive: true,
      })
      .catch(() => {
        /* best-effort client telemetry */
      });
  }

  private isSelectedDeviceFailure(error: unknown): boolean {
    const name = this.getErrorName(error);
    return name === 'NotFoundError' || name === 'OverconstrainedError';
  }

  private handleGetUserMediaError(error: unknown): void {
    const errorName = this.getErrorName(error);

    if (errorName === 'NotAllowedError') {
      this.onError(
        this.createRecorderError(
          'Microphone permission denied. Please allow microphone access and try again.',
          error,
        ),
      );
    } else if (errorName === 'NotFoundError') {
      this.onError(this.createRecorderError('No microphone found. Please connect a microphone and try again.', error));
    } else if (errorName === 'NotReadableError') {
      this.onError(
        this.createRecorderError(
          'Microphone is in use by another application. Please close other apps using the microphone.',
          error,
        ),
      );
    } else if (errorName === 'OverconstrainedError') {
      this.onError(this.createRecorderError('Selected microphone is unavailable. Please choose another microphone.', error));
    } else if (errorName === 'InvalidStateError') {
      this.onError(this.createRecorderError('Microphone is in an invalid state. Try reloading the page.', error));
    } else {
      this.onError(this.createRecorderError('Failed to access microphone', error));
    }
  }

  private createDeterministicMediaRecorder(audioBase64: string): MediaRecorder {
    const bytes = Uint8Array.from(atob(audioBase64), (char) => char.charCodeAt(0));

    const recorder = {
      mimeType: 'audio/wav',
      state: 'inactive' as RecordingState,
      ondataavailable: null as ((event: BlobEvent) => void) | null,
      onstop: null as ((event: Event) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      start() {
        recorder.state = 'recording';
      },
      stop() {
        if (recorder.state === 'inactive') {
          return;
        }

        recorder.state = 'inactive';
        const blob = new Blob([bytes], { type: recorder.mimeType });

        queueMicrotask(() => {
          recorder.ondataavailable?.({ data: blob } as BlobEvent);
          recorder.onstop?.(new Event('stop'));
        });
      },
      pause() {
        if (recorder.state === 'recording') {
          recorder.state = 'paused';
        }
      },
      resume() {
        if (recorder.state === 'paused') {
          recorder.state = 'recording';
        }
      },
    };

    return recorder as unknown as MediaRecorder;
  }

  async initialize(): Promise<void> {
    try {
      const playwrightAudioBase64 =
        typeof window !== 'undefined' ? window.__PLAYWRIGHT_VOICE_AUDIO_BASE64__ : undefined;
      const playwrightRecorderErrorName =
        typeof window !== 'undefined' ? window.__PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__ : undefined;

      if (typeof playwrightRecorderErrorName === 'string' && playwrightRecorderErrorName.length > 0) {
        delete window.__PLAYWRIGHT_VOICE_RECORDER_ERROR_NAME__;
        const recorderError = this.createRecorderError('Playwright injected recorder failure', {
          name: playwrightRecorderErrorName,
        });
        this.reportClientTelemetry('playwright-injected-recorder-failure', recorderError);
        this.onError(recorderError);
        return;
      }

      if (typeof playwrightAudioBase64 === 'string' && playwrightAudioBase64.length > 0) {
        this.stream = new MediaStream();
        this.mediaRecorder = this.createDeterministicMediaRecorder(playwrightAudioBase64);
      } else {
        if (typeof navigator === 'undefined') {
          const recorderError = new Error('navigator is undefined');
          this.reportClientTelemetry('navigator-unavailable', recorderError);
          this.onError(recorderError);
          return;
        }

        const hostname = window.location.hostname;
        const isLocalDevHost =
          hostname === 'localhost' ||
          hostname === '127.0.0.1' ||
          hostname === '::1' ||
          hostname === '[::1]';

        // Check if we're on HTTPS (required for getUserMedia outside local development).
        if (window.location.protocol !== 'https:' && !isLocalDevHost) {
          const recorderError = this.createRecorderError(
            'Microphone access requires HTTPS connection. Please use HTTPS or localhost.',
            { name: 'SecurityError' },
          );
          this.reportClientTelemetry('secure-context-check', recorderError);
          this.onError(recorderError);
          return;
        }

        // Check if mediaDevices is available
        if (!navigator.mediaDevices) {
          const recorderError = new Error(
            'navigator.mediaDevices is not available. Please ensure you are using a modern browser.',
          );
          this.reportClientTelemetry('media-devices-unavailable', recorderError);
          this.onError(recorderError);
          return;
        }

        // Normalize getUserMedia across browsers
        let getUserMediaFunc: ((c: MediaStreamConstraints) => Promise<MediaStream>) | null = null;

        if (navigator.mediaDevices?.getUserMedia) {
          getUserMediaFunc = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        } else {
          const legacy =
            (navigator as any).webkitGetUserMedia ||
            (navigator as any).mozGetUserMedia ||
            (navigator as any).msGetUserMedia;
          if (legacy) {
            getUserMediaFunc = (constraints: MediaStreamConstraints) =>
              new Promise((res, rej) => legacy.call(navigator, constraints, res, rej));
          }
        }

        if (!getUserMediaFunc) {
          const recorderError = new Error(
            'getUserMedia API is not available. Please check browser permissions.',
          );
          this.reportClientTelemetry('get-user-media-unavailable', recorderError);
          this.onError(recorderError);
          return;
        }

        // iOS-specific audio constraints
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;

        const audioConstraints = isIOS
          ? {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            }
          : {
              // Avoid exact sampleRate/channelCount: some Chrome builds keep the capture
              // pipeline (and tab mic indicator) active longer than necessary.
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            };

        const selectedDeviceId =
          typeof window !== 'undefined'
            ? window.localStorage.getItem(VoiceRecorder.SELECTED_MIC_DEVICE_ID_STORAGE_KEY)
            : null;
        const deviceIdMode = this.getDeviceIdMode(selectedDeviceId);
        const selectedAudioConstraints =
          selectedDeviceId && selectedDeviceId !== 'default'
            ? { ...audioConstraints, deviceId: { exact: selectedDeviceId } }
            : audioConstraints;

        try {
          this.stream = await getUserMediaFunc({ audio: selectedAudioConstraints });
        } catch (error) {
          if (selectedDeviceId && selectedDeviceId !== 'default' && this.isSelectedDeviceFailure(error)) {
            try {
              this.stream = await getUserMediaFunc({ audio: audioConstraints });
              window.localStorage.removeItem(VoiceRecorder.SELECTED_MIC_DEVICE_ID_STORAGE_KEY);
              this.reportClientTelemetry('get-user-media-selected-device', error, {
                deviceIdMode,
                retryWithDefaultDevice: true,
                retryOutcome: 'success',
              });
            } catch (retryError) {
              this.reportClientTelemetry('get-user-media-selected-device', error, {
                deviceIdMode,
                retryWithDefaultDevice: true,
                retryOutcome: 'failed',
                retryErrorName: this.getErrorName(retryError),
                retryErrorMessage: this.getErrorMessage(retryError),
              });
              this.reportClientTelemetry('get-user-media-default-retry', retryError, {
                deviceIdMode: 'default',
                retryWithDefaultDevice: false,
              });
              this.handleGetUserMediaError(retryError);
              return;
            }
          } else {
            this.reportClientTelemetry('get-user-media', error, {
              deviceIdMode,
              retryWithDefaultDevice: false,
            });
            this.handleGetUserMediaError(error);
            return;
          }
        }

        // Check if MediaRecorder is available
        if (typeof MediaRecorder === 'undefined') {
          const recorderError = new Error(
            'MediaRecorder API is not available. Please use a browser that supports audio recording.',
          );
          this.reportClientTelemetry('media-recorder-unavailable', recorderError, {
            deviceIdMode,
          });
          this.onError(recorderError);
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
          return;
        }

        const recorderResult = this.createMediaRecorder(this.stream);
        if (!recorderResult.recorder) {
          console.error('MediaRecorder creation failed:', recorderResult.error);
          const recorderError = this.createRecorderError(recorderResult.error, { name: 'NotSupportedError' });
          this.reportClientTelemetry('media-recorder-create', recorderError, {
            deviceIdMode,
          });
          this.onError(recorderError);
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
          return;
        }

        this.mediaRecorder = recorderResult.recorder;
      }

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        const audioBlob = new Blob(this.audioChunks, {
          type: mimeType,
        });
        this.onDataAvailable(audioBlob);
        this.audioChunks = [];

        // Always stop tracks after each segment so the browser mic indicator turns off.
        // (A boolean "release after stop" flag races with shouldListen flipping true before onstop.)
        this.teardownMicrophonePipeline();
        this.onHardwareReleased?.();
      };

      this.mediaRecorder.onerror = (event) => {
        const errorEvent = event as Event & { error?: unknown };
        const recorderError = this.createRecorderError('MediaRecorder error', errorEvent.error ?? event);
        this.reportClientTelemetry('media-recorder-runtime', recorderError, {
          recorderState: this.mediaRecorder?.state,
        });
        this.onError(recorderError);
      };
    } catch (error) {
      const recorderError = this.createRecorderError('Failed to initialize recorder', error);
      this.reportClientTelemetry('recorder-initialize', recorderError);
      this.onError(recorderError);
    }
  }

  start(): void {
    if (!this.mediaRecorder) {
      this.onError(new Error('Recorder not initialized'));
      return;
    }

    if (this.isRecording || this.mediaRecorder.state === 'recording') {
      this.onError(new Error('Already recording'));
      return;
    }

    if (this.mediaRecorder.state === 'paused') {
      // Resume instead of start if paused
      this.resume();
      return;
    }

    try {
      this.audioChunks = [];
      this.mediaRecorder.start();
      const recorderState = this.mediaRecorder.state as RecordingState;
      this.isRecording = recorderState === 'recording';
      if (!this.isRecording) {
        const recorderError = this.createRecorderError('MediaRecorder did not enter recording state', {
          name: 'InvalidStateError',
          message: `state=${recorderState}`,
        });
        this.reportClientTelemetry('media-recorder-start-state', recorderError, {
          recorderState,
        });
        this.onError(recorderError);
      }
    } catch (error) {
      this.isRecording = false;
      const recorderError = this.createRecorderError('Failed to start recording', error);
      this.reportClientTelemetry('media-recorder-start', recorderError, {
        recorderState: this.mediaRecorder.state,
      });
      this.onError(recorderError);
    }
  }

  stop(): void {
    if (!this.mediaRecorder || !this.isRecording) {
      return;
    }

    try {
      this.mediaRecorder.stop();
      this.isRecording = false;
    } catch (error) {
      const recorderError = this.createRecorderError('Failed to stop recording', error);
      this.reportClientTelemetry('media-recorder-stop', recorderError, {
        recorderState: this.mediaRecorder.state,
      });
      this.onError(recorderError);
    }
  }

  private teardownMicrophonePipeline(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.isRecording = false;
  }

  pause(): void {
    if (!this.mediaRecorder || !this.isRecording) {
      return;
    }

    try {
      this.mediaRecorder.pause();
    } catch (error) {
      const recorderError = this.createRecorderError('Failed to pause recording', error);
      this.reportClientTelemetry('media-recorder-pause', recorderError, {
        recorderState: this.mediaRecorder.state,
      });
      this.onError(recorderError);
    }
  }

  resume(): void {
    if (!this.mediaRecorder) {
      return;
    }

    try {
      this.mediaRecorder.resume();
    } catch (error) {
      const recorderError = this.createRecorderError('Failed to resume recording', error);
      this.reportClientTelemetry('media-recorder-resume', recorderError, {
        recorderState: this.mediaRecorder.state,
      });
      this.onError(recorderError);
    }
  }

  cleanup(): void {
    if (this.mediaRecorder) {
      if (this.isRecording) {
        this.stop();
      }
      this.mediaRecorder = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }

    this.audioChunks = [];
    this.isRecording = false;
  }

  getState(): RecordingState {
    if (!this.mediaRecorder) {
      return 'inactive';
    }
    return this.mediaRecorder.state;
  }

  isCurrentlyRecording(): boolean {
    return this.isRecording && this.mediaRecorder?.state === 'recording';
  }

  isInitialized(): boolean {
    return this.mediaRecorder !== null && this.stream !== null;
  }

  public getStream(): MediaStream | null {
    return this.stream;
  }

  private getCandidateMimeTypes(): string[] {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;

    const preferredTypes = isIOS ? [
      'audio/mp4',
      'audio/aac',
      'audio/mpeg',
      'audio/webm',
    ] : [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus',
      'audio/wav',
    ];

    if (typeof MediaRecorder.isTypeSupported !== 'function') {
      return [];
    }

    return preferredTypes.filter((mimeType) => {
      try {
        return MediaRecorder.isTypeSupported(mimeType);
      } catch {
        return false;
      }
    });
  }

  private createMediaRecorder(stream: MediaStream): {
    recorder: MediaRecorder | null;
    error: string;
  } {
    const errors: string[] = [];

    for (const mimeType of this.getCandidateMimeTypes()) {
      try {
        return {
          recorder: new MediaRecorder(stream, { mimeType }),
          error: '',
        };
      } catch (error: any) {
        errors.push(`${mimeType}: ${error?.message || error?.name || 'failed'}`);
      }
    }

    try {
      return {
        recorder: new MediaRecorder(stream),
        error: '',
      };
    } catch (error: any) {
      errors.push(`default: ${error?.message || error?.name || 'failed'}`);
    }

    return {
      recorder: null,
      error: `Microphone recording is not supported by this browser. MediaRecorder creation failed (${errors.join('; ') || 'no compatible format'}).`,
    };
  }

  // Static utility methods
  static async convertBlobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = reject;
      reader.readAsArrayBuffer(blob);
    });
  }

  static arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  static base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  }

  // Audio analysis utilities
  static async analyzeAudioLevel(blob: Blob): Promise<number> {
    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const arrayBuffer = await VoiceRecorder.convertBlobToArrayBuffer(blob);
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      
      const channelData = audioBuffer.getChannelData(0);
      let sum = 0;
      
      for (let i = 0; i < channelData.length; i++) {
        sum += Math.abs(channelData[i]);
      }
      
      const average = sum / channelData.length;
      audioContext.close();
      
      return average;
    } catch (error) {
      console.error('Error analyzing audio level:', error);
      return 0;
    }
  }

  static async detectSilence(blob: Blob, threshold = 0.01): Promise<boolean> {
    const level = await VoiceRecorder.analyzeAudioLevel(blob);
    return level < threshold;
  }

  // Duration utilities
  static async getAudioDuration(blob: Blob): Promise<number> {
    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const arrayBuffer = await blob.arrayBuffer();
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      
      const duration = audioBuffer.duration;
      await audioContext.close();
      
      return duration;
    } catch (error) {
      throw new Error(`Failed to get audio duration: ${error}`);
    }
  }

  // Format utilities
  static formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  static formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
}

// Types
export type RecordingState = 'inactive' | 'recording' | 'paused';

export interface RecordingOptions {
  channelCount?: number;
  sampleRate?: number;
  echoCancellation?: boolean;
  noiseSuppression?: boolean;
  autoGainControl?: boolean;
  mimeType?: string;
}

export interface AnalysisResult {
  level: number;
  duration: number;
  fileSize: number;
  isSilent: boolean;
}

// Advanced recorder with real-time analysis
export class AdvancedVoiceRecorder extends VoiceRecorder {
  private analyser: AnalyserNode | null = null;
  private audioContext: AudioContext | null = null;
  private dataArray: Uint8Array | null = null;
  private animationFrame: number | null = null;

  constructor(
    onDataAvailable: (audioBlob: Blob) => void,
    onError: (error: Error) => void,
    private onLevelUpdate?: (level: number) => void
  ) {
    super(onDataAvailable, onError);
  }

  async initialize(): Promise<void> {
    await super.initialize();

    if (this.stream) {
      this.setupRealTimeAnalysis();
    }
  }

  private setupRealTimeAnalysis(): void {
    if (!this.stream) return;

    try {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.8;
      
      source.connect(this.analyser);
      
      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      
      this.startAnalysis();
    } catch (error) {
      console.error('Failed to setup real-time analysis:', error);
    }
  }

  private startAnalysis(): void {
    if (!this.analyser || !this.dataArray) return;

    const analyze = () => {
      if (!this.analyser || !this.dataArray) return;

      this.analyser.getByteFrequencyData(this.dataArray as Uint8Array<ArrayBuffer>);
      
      // Calculate average level
      let sum = 0;
      for (let i = 0; i < this.dataArray.length; i++) {
        sum += this.dataArray[i];
      }
      const average = sum / this.dataArray.length;
      const level = average / 255; // Normalize to 0-1
      
      this.onLevelUpdate?.(level);
      
      if (this.isCurrentlyRecording()) {
        this.animationFrame = requestAnimationFrame(analyze);
      }
    };

    analyze();
  }

  start(): void {
    super.start();
    this.startAnalysis();
  }

  stop(): void {
    super.stop();
    
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
  }

  cleanup(): void {
    super.cleanup();
    
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    
    this.analyser = null;
    this.dataArray = null;
  }

  getCurrentLevel(): number {
    if (!this.analyser || !this.dataArray) return 0;

    this.analyser.getByteFrequencyData(this.dataArray as Uint8Array<ArrayBuffer>);
    
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
      sum += this.dataArray[i];
    }
    const average = sum / this.dataArray.length;
    return average / 255;
  }
}

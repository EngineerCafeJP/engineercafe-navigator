declare global {
  interface Window {
    __PLAYWRIGHT_VOICE_AUDIO_BASE64__?: string;
  }
}

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
  ) {}

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

      if (typeof playwrightAudioBase64 === 'string' && playwrightAudioBase64.length > 0) {
        this.stream = new MediaStream();
        this.mediaRecorder = this.createDeterministicMediaRecorder(playwrightAudioBase64);
      } else {
        if (typeof navigator === 'undefined') {
          this.onError(new Error('navigator is undefined'));
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
          this.onError(
            new Error(
              'Microphone access requires HTTPS connection. Please use HTTPS or localhost.',
            ),
          );
          return;
        }

        // Check if mediaDevices is available
        if (!navigator.mediaDevices) {
          this.onError(
            new Error(
              'navigator.mediaDevices is not available. Please ensure you are using a modern browser.',
            ),
          );
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
          this.onError(
            new Error('getUserMedia API is not available. Please check browser permissions.'),
          );
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

        try {
          const selectedDeviceId =
            typeof window !== 'undefined'
              ? window.localStorage.getItem(VoiceRecorder.SELECTED_MIC_DEVICE_ID_STORAGE_KEY)
              : null;
          const audio =
            selectedDeviceId && selectedDeviceId !== 'default'
              ? { ...audioConstraints, deviceId: { exact: selectedDeviceId } }
              : audioConstraints;
          this.stream = await getUserMediaFunc({ audio });
        } catch (error: any) {
          // Handle specific error cases
          if (error.name === 'NotAllowedError') {
            this.onError(
              new Error(
                'Microphone permission denied. Please allow microphone access and try again.',
              ),
            );
          } else if (error.name === 'NotFoundError') {
            this.onError(new Error('No microphone found. Please connect a microphone and try again.'));
          } else if (error.name === 'NotReadableError') {
            this.onError(
              new Error(
                'Microphone is in use by another application. Please close other apps using the microphone.',
              ),
            );
          } else if (error.name === 'OverconstrainedError') {
            this.onError(new Error('Selected microphone is unavailable. Please choose another microphone.'));
          } else {
            this.onError(new Error(`Failed to access microphone: ${error.message || error.name}`));
          }
          return;
        }

        // Check if MediaRecorder is available
        if (typeof MediaRecorder === 'undefined') {
          this.onError(
            new Error(
              'MediaRecorder API is not available. Please use a browser that supports audio recording.',
            ),
          );
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
          return;
        }

        const mimeType = this.getSupportedMimeType();
        const recorderOptions: MediaRecorderOptions = mimeType ? { mimeType } : {};

        try {
          this.mediaRecorder = new MediaRecorder(this.stream, recorderOptions);
        } catch (recorderError: any) {
          console.error('MediaRecorder creation failed:', recorderError);
          this.onError(
            new Error(`Failed to create MediaRecorder: ${recorderError.message || 'Unknown error'}`),
          );
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
          return;
        }
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
        this.onError(new Error(`MediaRecorder error: ${event}`));
      };
    } catch (error) {
      this.onError(new Error(`Failed to initialize recorder: ${error}`));
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
      this.isRecording = true;
    } catch (error) {
      this.isRecording = false;
      this.onError(new Error(`Failed to start recording: ${error}`));
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
      this.onError(new Error(`Failed to stop recording: ${error}`));
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
      this.onError(new Error(`Failed to pause recording: ${error}`));
    }
  }

  resume(): void {
    if (!this.mediaRecorder) {
      return;
    }

    try {
      this.mediaRecorder.resume();
    } catch (error) {
      this.onError(new Error(`Failed to resume recording: ${error}`));
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
    return this.isRecording;
  }

  isInitialized(): boolean {
    return this.mediaRecorder !== null && this.stream !== null;
  }

  public getStream(): MediaStream | null {
    return this.stream;
  }

  private getSupportedMimeType(): string {
    // Check if we're on iOS
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
    
    // iOS Safari prefers mp4/aac
    const mimeTypes = isIOS ? [
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

    for (const mimeType of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mimeType)) {
        return mimeType;
      }
    }

    // Fallback - let the browser choose
    console.warn('No supported mime type found, using default');
    return '';
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

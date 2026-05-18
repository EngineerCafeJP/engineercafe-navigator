import { VoiceRecorder } from './voice-recorder-core';

// Advanced recorder with real-time analysis
export class AdvancedVoiceRecorder extends VoiceRecorder {
  private analyser: AnalyserNode | null = null;
  private audioContext: AudioContext | null = null;
  private dataArray: Uint8Array | null = null;
  private animationFrame: number | null = null;

  constructor(
    onDataAvailable: (audioBlob: Blob) => void,
    onError: (error: Error) => void,
    private onLevelUpdate?: (level: number) => void,
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

declare module '@ricky0123/vad-react' {
  export interface RealTimeVADOptions {
    startOnLoad?: boolean;
    additionalAudioConstraints?: MediaTrackConstraints;
    onSpeechStart?: () => void;
    onSpeechEnd?: (audio: Float32Array) => void;
    onSpeechRealStart?: () => void;
    onVADMisfire?: () => void;
    onFrameProcessed?: (probabilities: { isSpeech: number; notSpeech: number }) => void;
    positiveSpeechThreshold?: number;
    negativeSpeechThreshold?: number;
    preSpeechPadFrames?: number;
    preSpeechPadMs?: number;
    redemptionFrames?: number;
    redemptionMs?: number;
    frameSamples?: number;
    minSpeechFrames?: number;
    minSpeechMs?: number;
    submitUserSpeechOnPause?: boolean;
    model?: 'legacy' | 'v5';
    userSpeakingThreshold?: number;
    workletURL?: string;
    modelURL?: string;
    baseAssetPath?: string;
    onnxWASMBasePath?: string;
    ortConfig?: unknown;
    workletOptions?: AudioWorkletNodeOptions;
    getStream?: () => Promise<MediaStream>;
    pauseStream?: (stream: MediaStream) => void;
    resumeStream?: (stream: MediaStream) => void;
    processorType?: string;
  }

  export interface MicVADResult {
    listening: boolean;
    errored: string | false;
    loading: boolean;
    userSpeaking: boolean;
    pause: () => Promise<void>;
    start: () => Promise<void>;
    toggle: () => Promise<void>;
  }

  export function useMicVAD(options: Partial<RealTimeVADOptions>): MicVADResult;

  export const utils: {
    encodeWAV: (samples: Float32Array, sampleRate?: number) => ArrayBuffer;
    float32To16BitPCM: (
      output: DataView,
      offset: number,
      input: Float32Array
    ) => void;
  };
}

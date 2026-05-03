import assert from 'node:assert/strict';

type Listener = () => void;

class MockAudioElement {
  public preload = '';
  public volume = 1;
  public src = '';
  public currentTime = 0;
  public duration = 1;
  public paused = true;
  public ended = false;
  private listeners = new Map<string, Set<Listener>>();

  setAttribute() {}
  removeAttribute() {}
  load() {}

  addEventListener(event: string, listener: Listener) {
    const listeners = this.listeners.get(event) ?? new Set<Listener>();
    listeners.add(listener);
    this.listeners.set(event, listeners);
  }

  removeEventListener(event: string, listener: Listener) {
    this.listeners.get(event)?.delete(listener);
  }

  async play() {
    this.paused = false;
    this.listeners.get('play')?.forEach((listener) => listener());
  }

  pause() {
    this.paused = true;
    this.listeners.get('pause')?.forEach((listener) => listener());
  }
}

class HangingAudioContext {
  public state = 'running' as AudioContextState;
  public destination = {};
  public sampleRate = 44_100;
  public currentTime = 0;

  async resume() {}
  async close() {
    this.state = 'closed';
  }

  createGain() {
    return { gain: { value: 1 }, connect() {} };
  }

  createBuffer() {
    return {};
  }

  createBufferSource() {
    return { buffer: null, connect() {}, start() {}, stop() {}, onended: null };
  }

  decodeAudioData() {
    return new Promise<AudioBuffer>(() => {});
  }
}

Object.defineProperty(globalThis, 'window', {
  value: {
    innerWidth: 390,
    AudioContext: HangingAudioContext,
    webkitAudioContext: HangingAudioContext,
    setTimeout,
    clearTimeout,
  },
  configurable: true,
});
Object.defineProperty(globalThis, 'document', {
  value: {
    addEventListener() {},
    removeEventListener() {},
  },
  configurable: true,
});
Object.defineProperty(globalThis, 'navigator', {
  value: {
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36',
    vendor: 'Google Inc.',
  },
  configurable: true,
});
Object.defineProperty(globalThis, 'Audio', { value: MockAudioElement, configurable: true });
Object.defineProperty(URL, 'createObjectURL', {
  value: () => 'blob:mock-audio',
  configurable: true,
});
Object.defineProperty(URL, 'revokeObjectURL', {
  value: () => {},
  configurable: true,
});

async function main() {
  const { AudioDataProcessor } = await import('../../src/lib/audio/audio-data-processor');
  const { MobileAudioService, DeviceDetector } = await import('../../src/lib/audio/mobile-audio-service');
  const { WebAudioPlayer } = await import('../../src/lib/audio/web-audio-player');

  const largeBase64 = 'A'.repeat(Math.ceil((AudioDataProcessor.LARGE_AUDIO_FALLBACK_THRESHOLD_BYTES + 16) / 3) * 4);
  assert.ok(
    AudioDataProcessor.estimateAudioDataSize(largeBase64) > AudioDataProcessor.LARGE_AUDIO_FALLBACK_THRESHOLD_BYTES,
  );
  assert.equal(DeviceDetector.getRecommendedAudioMethod(), 'html-audio');

  let didPlay = false;
  const service = new MobileAudioService({
    onPlay: () => {
      didPlay = true;
    },
  });
  const result = await service.playAudio(largeBase64);
  assert.equal(result.success, true);
  assert.equal(result.method, 'html-audio');
  assert.equal(didPlay, true);

  const player = new WebAudioPlayer({ decodeTimeoutMs: 10 } as never);
  const loadResult = await player.loadAudioData('UklGRiQAAABXQVZFZm10IBAAAAABAAEA');
  assert.equal(loadResult.success, false);
  assert.match(loadResult.error?.message ?? '', /timed out/);

  console.log('Android audio fallback checks passed.');
}

void main();

import path from 'node:path';
import { readFile } from 'node:fs/promises';
import type { Page } from '@playwright/test';

/**
 * Install deterministic stubs for navigator.mediaDevices.getUserMedia and
 * window.MediaRecorder so the kiosk voice pipeline consumes a committed WAV
 * fixture instead of real microphone data.
 *
 * Must be called BEFORE `page.goto(...)` so the init script runs on the
 * very first document the browser loads.
 *
 * The FakeMediaRecorder mirrors the API surface that
 * `frontend/src/lib/voice-recorder.ts` actually touches:
 *   - constructor(stream, { mimeType })
 *   - start() / stop() / pause() / resume() / requestData()
 *   - state property ('inactive' | 'recording' | 'paused')
 *   - mimeType property
 *   - ondataavailable / onstop / onerror / onstart / onpause / onresume
 *   - addEventListener / removeEventListener
 *   - static isTypeSupported()
 */
export async function installVoiceMediaMocks(page: Page): Promise<void> {
  const wavPath = path.join(__dirname, '..', 'fixtures', 'voice', 'sample.wav');
  const wavBase64 = (await readFile(wavPath)).toString('base64');

  await page.addInitScript((b64: string) => {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const fixtureBlob = new Blob([bytes], { type: 'audio/wav' });

    const noop = () => {};
    const buildTrack = () =>
      ({
        kind: 'audio',
        id: 'fake-audio-track',
        label: 'Fake Microphone',
        enabled: true,
        muted: false,
        readyState: 'live',
        contentHint: '',
        isolated: false,
        onended: null,
        onmute: null,
        onunmute: null,
        onisolationchange: null,
        clone: () => buildTrack(),
        stop: noop,
        getCapabilities: () => ({}),
        getConstraints: () => ({}),
        getSettings: () => ({}),
        applyConstraints: async () => undefined,
        addEventListener: noop,
        removeEventListener: noop,
        dispatchEvent: () => true,
      }) as unknown as MediaStreamTrack;

    const buildStream = () => {
      const track = buildTrack();
      return {
        id: 'fake-audio-stream',
        active: true,
        onaddtrack: null,
        onremovetrack: null,
        getTracks: () => [track],
        getAudioTracks: () => [track],
        getVideoTracks: () => [],
        getTrackById: () => track,
        addTrack: noop,
        removeTrack: noop,
        clone: () => buildStream(),
        addEventListener: noop,
        removeEventListener: noop,
        dispatchEvent: () => true,
      } as unknown as MediaStream;
    };

    if (!('mediaDevices' in navigator) || !navigator.mediaDevices) {
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: {},
      });
    }
    const mediaDevices = navigator.mediaDevices as unknown as {
      getUserMedia: (constraints?: MediaStreamConstraints) => Promise<MediaStream>;
      enumerateDevices: () => Promise<MediaDeviceInfo[]>;
      addEventListener?: (...args: unknown[]) => void;
      removeEventListener?: (...args: unknown[]) => void;
    };
    mediaDevices.getUserMedia = async () => buildStream();
    mediaDevices.enumerateDevices = async () =>
      [
        {
          deviceId: 'fake-audio-input',
          kind: 'audioinput',
          label: 'Fake Microphone',
          groupId: 'fake-group',
          toJSON: () => ({}),
        },
      ] as unknown as MediaDeviceInfo[];
    if (!mediaDevices.addEventListener) {
      mediaDevices.addEventListener = noop;
    }
    if (!mediaDevices.removeEventListener) {
      mediaDevices.removeEventListener = noop;
    }

    type RecorderState = 'inactive' | 'recording' | 'paused';

    class FakeMediaRecorder {
      static isTypeSupported(_mimeType: string): boolean {
        return true;
      }

      readonly stream: MediaStream;
      mimeType: string;
      state: RecorderState = 'inactive';
      audioBitsPerSecond = 128000;
      videoBitsPerSecond = 0;

      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onstart: ((event: Event) => void) | null = null;
      onpause: ((event: Event) => void) | null = null;
      onresume: ((event: Event) => void) | null = null;

      constructor(stream: MediaStream, options?: MediaRecorderOptions) {
        this.stream = stream;
        this.mimeType = options?.mimeType ?? 'audio/wav';
      }

      start(_timeslice?: number): void {
        this.state = 'recording';
        setTimeout(() => {
          try {
            this.onstart?.(new Event('start'));
          } catch {
            /* noop */
          }
        }, 0);
      }

      stop(): void {
        if (this.state === 'inactive') {
          return;
        }
        this.state = 'inactive';
        setTimeout(() => {
          try {
            this.ondataavailable?.({ data: fixtureBlob });
          } catch {
            /* noop */
          }
          try {
            this.onstop?.(new Event('stop'));
          } catch {
            /* noop */
          }
        }, 20);
      }

      pause(): void {
        if (this.state === 'recording') {
          this.state = 'paused';
          try {
            this.onpause?.(new Event('pause'));
          } catch {
            /* noop */
          }
        }
      }

      resume(): void {
        if (this.state === 'paused') {
          this.state = 'recording';
          try {
            this.onresume?.(new Event('resume'));
          } catch {
            /* noop */
          }
        }
      }

      requestData(): void {
        try {
          this.ondataavailable?.({ data: fixtureBlob });
        } catch {
          /* noop */
        }
      }

      addEventListener(type: string, listener: EventListener): void {
        const prop = `on${type}` as keyof FakeMediaRecorder;
        // @ts-expect-error dynamic assignment mirrors DOM behaviour
        this[prop] = listener;
      }

      removeEventListener(type: string): void {
        const prop = `on${type}` as keyof FakeMediaRecorder;
        // @ts-expect-error dynamic assignment mirrors DOM behaviour
        this[prop] = null;
      }

      dispatchEvent(_event: Event): boolean {
        return true;
      }
    }

    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      writable: true,
      value: FakeMediaRecorder,
    });
  }, wavBase64);
}

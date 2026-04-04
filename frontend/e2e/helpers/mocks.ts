import { type Page } from '@playwright/test';

/**
 * Knowledge エントリのモックデータ
 */
export const MOCK_KNOWLEDGE_ENTRY = {
  id: 'entry-001',
  title: 'WiFiパスワード',
  content: 'WiFiのパスワードは1234です',
  category: '設備',
  subcategory: 'WiFi',
  language: 'ja',
  source: '内部Wiki',
  metadata: {},
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-06-01T12:00:00Z',
};

/**
 * Knowledge 一覧レスポンスのモックデータ
 */
export const MOCK_KNOWLEDGE_LIST = {
  data: [MOCK_KNOWLEDGE_ENTRY],
  total: 1,
  page: 1,
  limit: 20,
};

/**
 * Knowledge エディタ設定のモックデータ
 */
export const MOCK_EDITOR_CONFIG = {
  categories: ['設備', '基本情報', 'イベント'],
  subcategories: {
    '設備': ['会議室', 'WiFi'],
    '基本情報': ['営業時間', '所在地'],
    'イベント': ['今後のイベント'],
  },
  sources: ['内部Wiki', '構造化データ'],
  languages: ['ja', 'en'],
  templates: {
    default: { title: '', importance: 'medium', tags: '' },
    '設備': { title: '', importance: 'high', tags: '' },
  },
};

/**
 * Marp レスポンスのモックデータ
 */
export const MOCK_MARP_RESPONSE = {
  success: true,
  html: `<!DOCTYPE html><html><head><title>Slides</title></head><body>
    <div class="marpit">
      <svg id="slide1"><text>Slide 1 Content</text></svg>
      <svg id="slide2"><text>Slide 2 Content</text></svg>
      <svg id="slide3"><text>Slide 3 Content</text></svg>
    </div>
  </body></html>`,
  slideData: {
    slides: [
      { slideNumber: 1, title: 'スライド1', content: '内容1', notes: 'ノート1' },
      { slideNumber: 2, title: 'スライド2', content: '内容2', notes: '' },
      { slideNumber: 3, title: 'スライド3', content: '内容3', notes: '' },
    ],
  },
  narrationData: {
    metadata: { title: 'テスト', language: 'ja', speaker: 'sakura', version: '1' },
    slides: [
      {
        slideNumber: 1,
        narration: { auto: 'ナレーション1', onEnter: '', onDemand: {} },
        transitions: { next: 'next', previous: null },
      },
      {
        slideNumber: 2,
        narration: { auto: 'ナレーション2', onEnter: '', onDemand: {} },
        transitions: { next: 'next', previous: 'prev' },
      },
      {
        slideNumber: 3,
        narration: { auto: '', onEnter: '', onDemand: {} },
        transitions: { next: null, previous: 'prev' },
      },
    ],
  },
  slideCount: 3,
  metadata: { title: 'テストスライド', language: 'ja' },
};

/**
 * 音声レスポンスのモックデータ
 * 最小の有効な MP3: ID3 ヘッダ + 1フレーム（無音）
 */
export const MOCK_VOICE_RESPONSE = {
  success: true,
  audioResponse:
    'SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4LjI5LjEwMAAAAAAAAAAAAAAA//OEAAAAAAAAAAAASW5mbwAAAA8AAAAEAAABIADAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAAAAJMYXZjNTguNTQAAAAAAAAAAAAAAAAkAAAAAAAAAAABIIJ4AAAAAAAAAAAAAAAAAAAAAP/zhAAAAAAAAAAAAAAAAAAAAAAAAEluZm8AAAAPAAAABAAAASAAw',
};

/**
 * Knowledge API ルートをモック
 */
export async function setupKnowledgeMocks(page: Page) {
  // editor-config エンドポイント
  await page.route('/api/admin/knowledge/editor-config', (route) =>
    route.fulfill({ json: MOCK_EDITOR_CONFIG }),
  );

  // 個別エントリ取得・更新・削除
  await page.route('/api/admin/knowledge/entry-001', (route) => {
    const method = route.request().method();
    if (method === 'GET') {
      return route.fulfill({ json: MOCK_KNOWLEDGE_ENTRY });
    } else if (method === 'DELETE') {
      return route.fulfill({ json: { success: true } });
    }
    return route.continue();
  });

  // 一覧取得・作成
  await page.route('/api/admin/knowledge', (route) => {
    const method = route.request().method();
    if (method === 'GET') {
      return route.fulfill({ json: MOCK_KNOWLEDGE_LIST });
    } else if (method === 'POST') {
      return route.fulfill({ status: 201, json: { ...MOCK_KNOWLEDGE_ENTRY, id: 'new-001' } });
    }
    return route.continue();
  });
}

/**
 * Marp API ルートをモック
 */
export async function setupMarpMocks(page: Page) {
  await page.route('/api/marp', (route) => route.fulfill({ json: MOCK_MARP_RESPONSE }));

  await page.route('/api/voice', (route) => route.fulfill({ json: MOCK_VOICE_RESPONSE }));

  await page.route('/api/slides', (route) =>
    route.fulfill({ json: { success: true } }),
  );
}

/**
 * Web Audio API をスタブ化
 * AudioContext と関連する Web Audio API をモック化してブラウザに注入
 */
export async function setupWebAudioMock(page: Page) {
  await page.addInitScript(() => {
    // Mock AudioBuffer
    class MockAudioBuffer {
      duration = 0.01;
      length = 441;
      numberOfChannels = 1;
      sampleRate = 44100;

      getChannelData() {
        return new Float32Array(441);
      }

      copyFromChannel() {}
      copyToChannel() {}
    }

    // Mock BufferSource
    class MockBufferSource {
      buffer: unknown = null;
      onended: (() => void) | null = null;

      connect() {
        return this;
      }

      start() {
        // 10ms後にonendedを呼び出して再生完了をシミュレート
        setTimeout(() => {
          this.onended?.();
        }, 10);
      }

      stop() {}
      disconnect() {}

      addEventListener(event: string, cb: () => void) {
        if (event === 'ended') this.onended = cb;
      }

      removeEventListener() {}
    }

    // Mock GainNode
    class MockGainNode {
      gain = { value: 1, setValueAtTime() {}, linearRampToValueAtTime() {} };

      connect() {
        return this;
      }

      disconnect() {}
    }

    // Mock AudioContext
    class MockAudioContext {
      state = 'running';
      sampleRate = 44100;
      currentTime = 0;
      destination = { connect() {} };

      createBufferSource() {
        return new MockBufferSource();
      }

      createGain() {
        return new MockGainNode();
      }

      decodeAudioData(_ab: ArrayBuffer, success?: (b: MockAudioBuffer) => void) {
        const buf = new MockAudioBuffer();
        if (success) {
          setTimeout(() => success(buf), 5);
        }
        return Promise.resolve(buf);
      }

      async resume() {}
      async close() {}
    }

    // @ts-ignore
    window.AudioContext = MockAudioContext;
    // @ts-ignore
    window.webkitAudioContext = MockAudioContext;
  });
}

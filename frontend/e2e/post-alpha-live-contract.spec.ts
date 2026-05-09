import { expect, test, type APIRequestContext, type APIResponse } from '@playwright/test';

const postAlphaLive = process.env.PLAYWRIGHT_POST_ALPHA_LIVE === '1';

type JsonObject = Record<string, unknown>;

async function readJson(response: APIResponse): Promise<JsonObject> {
  return (await response.json()) as JsonObject;
}

async function testRequestPost(
  request: APIRequestContext,
  path: string,
  data: JsonObject,
) {
  return request.post(path, {
    data,
    timeout: 90_000,
  });
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function object(value: unknown): JsonObject {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject) : {};
}

test.describe('Post-alpha live production contracts', () => {
  test.skip(
    !postAlphaLive,
    'Set PLAYWRIGHT_POST_ALPHA_LIVE=1 and PLAYWRIGHT_BASE_URL to verify live production contracts.',
  );

  test('keeps production TTS pinned to Piper Plus with no provider fallback', async ({ request }) => {
    const configResponse = await request.get('/api/voice', { timeout: 30_000 });
    expect(configResponse.ok()).toBeTruthy();
    const config = (await configResponse.json()) as {
      defaultTtsProvider?: unknown;
      ttsProviderOverrideEnabled?: unknown;
      ttsProviders?: unknown;
    };

    expect(config.defaultTtsProvider).toBe('piper');
    expect(config.ttsProviderOverrideEnabled).toBe(false);
    expect(config.ttsProviders).toEqual([{ id: 'piper', label: 'Piper-plus' }]);

    const ttsResponse = await testRequestPost(request, '/api/voice', {
      action: 'text_to_speech',
      text: 'カフェの営業時間をご案内します。',
      language: 'ja',
      sessionId: `post-alpha-live-piper-${Date.now()}`,
    });
    expect(ttsResponse.ok()).toBeTruthy();
    const tts = await readJson(ttsResponse);
    const upstream = object(tts.upstreamStatus);

    expect(tts.success).toBe(true);
    expect(text(tts.audioResponse).length).toBeGreaterThan(1_000);
    expect(upstream.provider).toBe('piper');
    expect(upstream.actualProvider).toBe('piper');
    expect(upstream.fallbackUsed).not.toBe(true);

    const fillerResponse = await testRequestPost(request, '/api/voice/filler', {
      query: '少し考えてください',
      language: 'ja',
    });
    expect(fillerResponse.ok()).toBeTruthy();
    const filler = await readJson(fillerResponse);
    const fillerUpstream = object(filler.upstreamStatus);

    expect(filler.phase).toBe('filler');
    expect(text(filler.audioResponse).length).toBeGreaterThan(8_000);
    expect(fillerUpstream.ok).toBe(true);
  });

  test('routes bare cafe questions to Saino and coworking/event context to Engineer Cafe', async ({
    request,
  }) => {
    const sessionId = `post-alpha-live-cafe-${Date.now()}`;

    async function ask(question: string): Promise<string> {
      const response = await testRequestPost(request, '/api/qa', {
        question,
        language: 'ja',
        sessionId,
      });
      expect(response.ok()).toBeTruthy();
      const payload = await readJson(response);
      expect(payload.success).toBe(true);
      return text(payload.answer);
    }

    const bareCafe = await ask('カフェの営業時間は？');
    expect(bareCafe).toMatch(/cafe&bar\s*saino|サイノ|saino/i);

    const coworking = await ask('コワーキングスペースの営業時間は？');
    expect(coworking).toMatch(/エンジニアカフェ|コワーキング|Engineer Cafe/i);
    expect(coworking).not.toMatch(/cafe&bar\s*saino|サイノ/i);

    const eventCafe = await ask('カフェでイベントはできますか？');
    expect(eventCafe).toMatch(/イベント|開催|ワークショップ|エンジニア/i);
    expect(eventCafe).not.toMatch(/cafe&bar\s*saino|サイノ/i);

    const neighboringCafe = await ask('隣のカフェの営業時間は？');
    expect(neighboringCafe).toMatch(/cafe&bar\s*saino|サイノ|saino/i);
  });
});

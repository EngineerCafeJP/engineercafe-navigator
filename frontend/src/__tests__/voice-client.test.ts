import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import {
  interruptVoiceSession,
  requestVoiceFiller,
  sendVoiceClientTelemetry,
  speechToText,
  textToSpeech,
} from '../lib/api/voice-client';

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
});

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('speechToText posts typed speech_to_text payload and forwards AbortSignal', async () => {
  const controller = new AbortController();
  let capturedUrl: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;
  let capturedBody: Record<string, unknown> | null = null;

  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      success: true,
      transcript: 'こんにちは',
      detectedLanguage: 'ja',
      confidence: 0.91,
      sttProvider: 'qwen-primary',
      sttPostprocessed: true,
      sessionId: 'session-1',
      requestId: 'req-1',
      phase: 'speech_to_text',
    });
  }) as typeof fetch;

  const result = await speechToText(
    {
      audioData: 'UklGRg==',
      language: 'ja',
      sessionId: 'session-1',
      conversationStage: 'reception',
    },
    { signal: controller.signal },
  );

  assert.equal(capturedUrl, '/api/voice');
  assert.equal(capturedInit?.method, 'POST');
  assert.equal(new Headers(capturedInit?.headers).get('Content-Type'), 'application/json');
  assert.equal(capturedInit?.signal, controller.signal);
  assert.deepEqual(capturedBody, {
    action: 'speech_to_text',
    audioData: 'UklGRg==',
    language: 'ja',
    sessionId: 'session-1',
    conversationStage: 'reception',
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(result.data.success, true);
  assert.equal(result.data.transcript, 'こんにちは');
  assert.equal(result.data.sttPostprocessed, true);
});

test('textToSpeech posts typed text_to_speech payload and normalizes vrmControl', async () => {
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (_input, init) => {
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      success: true,
      audioResponse: 'base64-audio',
      audioFormat: 'audio/wav',
      emotion: 'happy',
      cleanText: 'こんにちは',
      vrmControl: { name: 'talking', duration: 800 },
      phase: 'text_to_speech',
    });
  }) as typeof fetch;

  const result = await textToSpeech({
    text: 'こんにちは',
    language: 'ja',
    sessionId: 'session-1',
    emotion: 'happy',
    outputEncoding: 'mp3',
    ttsProvider: 'piper',
    includeVrmControl: true,
  });

  assert.deepEqual(capturedBody, {
    action: 'text_to_speech',
    text: 'こんにちは',
    language: 'ja',
    sessionId: 'session-1',
    streaming: false,
    emotion: 'happy',
    outputEncoding: 'mp3',
    ttsProvider: 'piper',
    includeVrmControl: true,
  });
  assert.equal(result.data.success, true);
  assert.equal(result.data.audioResponse, 'base64-audio');
  assert.deepEqual(result.data.vrmControl, { name: 'talking', duration: 800 });
});

test('textToSpeech includes speed in payload when provided', async () => {
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (_input, init) => {
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      success: true,
      audioResponse: 'base64-audio',
      audioFormat: 'audio/wav',
      phase: 'text_to_speech',
    });
  }) as typeof fetch;

  await textToSpeech({
    text: 'Hello',
    language: 'en',
    sessionId: 'session-1',
    ttsProvider: 'piper',
    speed: 0.65,
  });

  assert.deepEqual(capturedBody, {
    action: 'text_to_speech',
    text: 'Hello',
    language: 'en',
    sessionId: 'session-1',
    streaming: false,
    ttsProvider: 'piper',
    speed: 0.65,
  });
});

test('textToSpeech omits speed when not provided', async () => {
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (_input, init) => {
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      success: true,
      audioResponse: 'base64-audio',
      audioFormat: 'audio/wav',
      phase: 'text_to_speech',
    });
  }) as typeof fetch;

  await textToSpeech({
    text: 'Hello',
    language: 'en',
    sessionId: 'session-1',
    ttsProvider: 'piper',
  });

  assert.equal('speed' in (capturedBody ?? {}), false);
});

test('textToSpeech returns normalized error payload for backend failures', async () => {
  global.fetch = (async () => jsonResponse({ detail: 'Missing text for text_to_speech' }, 400)) as typeof fetch;

  const result = await textToSpeech({ text: '', language: 'ja' });

  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
  assert.deepEqual(result.data, {
    success: false,
    error: 'Missing text for text_to_speech',
    requestId: undefined,
    phase: undefined,
    upstreamStatus: null,
  });
});

test('sendVoiceClientTelemetry posts to dedicated telemetry route with keepalive', async () => {
  let capturedUrl: string | URL | Request | undefined;
  let capturedInit: RequestInit | undefined;
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedInit = init;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({ success: true });
  }) as typeof fetch;

  const result = await sendVoiceClientTelemetry(
    {
      action: 'caller-provided-action',
      event: 'voice_recorder_error',
      phase: 'start',
      sessionId: 'session-1',
      errorName: 'NotFoundError',
    },
    { keepalive: true },
  );

  assert.equal(capturedUrl, '/api/telemetry/voice');
  assert.equal(capturedInit?.keepalive, true);
  assert.deepEqual(capturedBody, {
    event: 'voice_recorder_error',
    phase: 'start',
    sessionId: 'session-1',
    errorName: 'NotFoundError',
  });
  assert.equal(result.ok, true);
  assert.equal(result.data.success, true);
});

test('interruptVoiceSession posts best-effort interrupt payload with keepalive', async () => {
  let capturedInit: RequestInit | undefined;
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (_input, init) => {
    capturedInit = init;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({ success: true });
  }) as typeof fetch;

  const result = await interruptVoiceSession(
    {
      sessionId: 'session-1',
      language: 'ja',
    },
    { keepalive: true },
  );

  assert.equal(capturedInit?.keepalive, true);
  assert.deepEqual(capturedBody, {
    action: 'interrupt',
    sessionId: 'session-1',
    language: 'ja',
  });
  assert.equal(result.ok, true);
  assert.equal(result.data.success, true);
});

test('requestVoiceFiller posts filler payload and normalizes success-less backend body', async () => {
  let capturedUrl: string | URL | Request | undefined;
  let capturedBody: Record<string, unknown> | null = null;
  global.fetch = (async (input, init) => {
    capturedUrl = input;
    capturedBody =
      typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null;

    return jsonResponse({
      audioResponse: 'filler-audio',
      intent: 'fallback',
      audioFormat: 'audio/wav',
      fillerText: '少々お待ちください',
      source: 'static',
      requestId: 'req-filler',
      phase: 'filler',
    });
  }) as typeof fetch;

  const result = await requestVoiceFiller({
    query: '営業時間は？',
    language: 'ja',
    sessionId: 'session-1',
  });

  assert.equal(capturedUrl, '/api/voice/filler');
  assert.deepEqual(capturedBody, {
    query: '営業時間は？',
    language: 'ja',
    sessionId: 'session-1',
  });
  assert.equal(result.data.success, true);
  assert.equal(result.data.audioResponse, 'filler-audio');
  assert.equal(result.data.intent, 'fallback');
  assert.equal(result.data.requestId, 'req-filler');
});

test('requestVoiceFiller handles non-JSON error bodies with fallback message', async () => {
  global.fetch = (async () => new Response('bad gateway', { status: 502 })) as typeof fetch;

  const result = await requestVoiceFiller({ query: 'hello', language: 'en' });

  assert.equal(result.ok, false);
  assert.equal(result.status, 502);
  assert.equal(result.data.success, false);
  assert.equal(result.data.error, 'フィラー音声の取得に失敗しました');
});

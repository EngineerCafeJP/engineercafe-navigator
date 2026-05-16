export type VoiceLanguage = 'ja' | 'en' | 'zh' | 'ko';

export interface VoiceClientOptions {
  readonly signal?: AbortSignal;
  readonly keepalive?: boolean;
}

export interface VoiceClientResult<TPayload> {
  readonly ok: boolean;
  readonly status: number;
  readonly data: TPayload;
}

export interface VoiceBasePayload {
  readonly success: boolean;
  readonly error?: string;
  readonly sessionId?: string;
  readonly requestId?: string;
  readonly phase?: string;
  readonly upstreamStatus?: Record<string, unknown> | null;
}

export interface SpeechToTextRequest {
  readonly audioData: string;
  readonly language?: VoiceLanguage;
  readonly sessionId?: string;
  readonly conversationStage?: string;
}

export interface SpeechToTextPayload extends VoiceBasePayload {
  readonly transcript?: string;
  readonly emotion?: string;
  readonly detectedLanguage?: string;
  readonly confidence?: number;
  readonly sttProvider?: string;
  readonly sttPostprocessed?: boolean;
}

export interface TextToSpeechRequest {
  readonly text: string;
  readonly language?: VoiceLanguage;
  readonly sessionId?: string;
  readonly streaming?: boolean;
  readonly emotion?: string;
  readonly outputEncoding?: string;
  readonly ttsProvider?: string;
  readonly includeVrmControl?: boolean;
}

export interface TextToSpeechPayload extends VoiceBasePayload {
  readonly audioResponse?: string;
  readonly audioFormat?: string;
  readonly emotion?: string;
  readonly cleanText?: string;
  readonly vrmControl?: Record<string, unknown> | null;
}

export interface VoiceClientTelemetryRequest {
  readonly event?: unknown;
  readonly phase?: unknown;
  readonly sessionId?: unknown;
  readonly userAgent?: unknown;
  readonly errorName?: unknown;
  readonly errorMessage?: unknown;
  readonly deviceIdMode?: unknown;
  readonly recorderState?: unknown;
  readonly retryWithDefaultDevice?: unknown;
  readonly retryOutcome?: unknown;
  readonly retryErrorName?: unknown;
  readonly retryErrorMessage?: unknown;
  readonly timestamp?: unknown;
  readonly [key: string]: unknown;
}

export interface VoiceClientTelemetryPayload extends VoiceBasePayload {}

export interface VoiceInterruptRequest {
  readonly sessionId: string;
  readonly language?: VoiceLanguage;
}

export interface VoiceInterruptPayload extends VoiceBasePayload {}

export interface VoiceFillerRequest {
  readonly query: string;
  readonly language: VoiceLanguage;
  readonly sessionId?: string;
}

export interface VoiceFillerPayload extends VoiceBasePayload {
  readonly audioResponse?: string;
  readonly intent?: string;
  readonly audioFormat?: string;
  readonly fillerText?: string;
  readonly source?: string;
}

const VOICE_PATH = '/api/voice';
const VOICE_FILLER_PATH = '/api/voice/filler';

async function readJson(response: Response): Promise<Record<string, unknown>> {
  try {
    const data = await response.json();
    return data && typeof data === 'object' ? (data as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function errorMessage(data: Record<string, unknown>, fallback: string): string {
  const error = data.error ?? data.detail ?? data.message;
  return typeof error === 'string' && error.trim() ? error : fallback;
}

function optionalString(data: Record<string, unknown>, key: string): string | undefined {
  const value = data[key];
  return typeof value === 'string' ? value : undefined;
}

function optionalNumber(data: Record<string, unknown>, key: string): number | undefined {
  const value = data[key];
  return typeof value === 'number' ? value : undefined;
}

function optionalBoolean(data: Record<string, unknown>, key: string): boolean | undefined {
  const value = data[key];
  return typeof value === 'boolean' ? value : undefined;
}

function optionalRecord(data: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const value = data[key];
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function normalizeBasePayload<TPayload extends VoiceBasePayload>(
  response: Response,
  data: Record<string, unknown>,
  fallbackError: string,
  payload: Omit<TPayload, keyof VoiceBasePayload>,
): TPayload {
  if (!response.ok) {
    return {
      success: false,
      error: errorMessage(data, fallbackError),
      requestId: optionalString(data, 'requestId'),
      phase: optionalString(data, 'phase'),
      upstreamStatus: optionalRecord(data, 'upstreamStatus'),
    } as TPayload;
  }

  return {
    ...payload,
    success: data.success !== false,
    error: optionalString(data, 'error'),
    sessionId: optionalString(data, 'sessionId'),
    requestId: optionalString(data, 'requestId'),
    phase: optionalString(data, 'phase'),
    upstreamStatus: optionalRecord(data, 'upstreamStatus'),
  } as TPayload;
}

async function postJson(
  url: string,
  body: Record<string, unknown>,
  options: VoiceClientOptions,
): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal: options.signal,
    keepalive: options.keepalive,
  });
}

function normalizeSpeechToTextPayload(
  response: Response,
  data: Record<string, unknown>,
): SpeechToTextPayload {
  return normalizeBasePayload<SpeechToTextPayload>(
    response,
    data,
    '音声認識に失敗しました',
    {
      transcript: optionalString(data, 'transcript'),
      emotion: optionalString(data, 'emotion'),
      detectedLanguage: optionalString(data, 'detectedLanguage'),
      confidence: optionalNumber(data, 'confidence'),
      sttProvider: optionalString(data, 'sttProvider'),
      sttPostprocessed: optionalBoolean(data, 'sttPostprocessed'),
    },
  );
}

function normalizeTextToSpeechPayload(
  response: Response,
  data: Record<string, unknown>,
): TextToSpeechPayload {
  return normalizeBasePayload<TextToSpeechPayload>(
    response,
    data,
    '音声の生成に失敗しました',
    {
      audioResponse: optionalString(data, 'audioResponse'),
      audioFormat: optionalString(data, 'audioFormat'),
      emotion: optionalString(data, 'emotion'),
      cleanText: optionalString(data, 'cleanText'),
      vrmControl: optionalRecord(data, 'vrmControl'),
    },
  );
}

function normalizeClientTelemetryPayload(
  response: Response,
  data: Record<string, unknown>,
): VoiceClientTelemetryPayload {
  return normalizeBasePayload<VoiceClientTelemetryPayload>(
    response,
    data,
    'クライアントテレメトリの送信に失敗しました',
    {},
  );
}

function normalizeInterruptPayload(
  response: Response,
  data: Record<string, unknown>,
): VoiceInterruptPayload {
  return normalizeBasePayload<VoiceInterruptPayload>(
    response,
    data,
    '音声セッションの停止に失敗しました',
    {},
  );
}

function normalizeFillerPayload(
  response: Response,
  data: Record<string, unknown>,
): VoiceFillerPayload {
  return normalizeBasePayload<VoiceFillerPayload>(
    response,
    data,
    'フィラー音声の取得に失敗しました',
    {
      audioResponse: optionalString(data, 'audioResponse'),
      intent: optionalString(data, 'intent'),
      audioFormat: optionalString(data, 'audioFormat'),
      fillerText: optionalString(data, 'fillerText'),
      source: optionalString(data, 'source'),
    },
  );
}

export async function speechToText(
  request: SpeechToTextRequest,
  options: VoiceClientOptions = {},
): Promise<VoiceClientResult<SpeechToTextPayload>> {
  const response = await postJson(
    VOICE_PATH,
    {
      action: 'speech_to_text',
      audioData: request.audioData,
      language: request.language ?? 'ja',
      sessionId: request.sessionId,
      conversationStage: request.conversationStage,
    },
    options,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeSpeechToTextPayload(response, data),
  };
}

export async function textToSpeech(
  request: TextToSpeechRequest,
  options: VoiceClientOptions = {},
): Promise<VoiceClientResult<TextToSpeechPayload>> {
  const response = await postJson(
    VOICE_PATH,
    {
      action: 'text_to_speech',
      text: request.text,
      language: request.language ?? 'ja',
      sessionId: request.sessionId,
      streaming: request.streaming ?? false,
      ...(typeof request.emotion === 'string' && request.emotion.length > 0
        ? { emotion: request.emotion }
        : {}),
      ...(typeof request.outputEncoding === 'string' && request.outputEncoding.length > 0
        ? { outputEncoding: request.outputEncoding }
        : {}),
      ...(typeof request.ttsProvider === 'string' && request.ttsProvider.length > 0
        ? { ttsProvider: request.ttsProvider }
        : {}),
      ...(request.includeVrmControl === true ? { includeVrmControl: true } : {}),
    },
    options,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeTextToSpeechPayload(response, data),
  };
}

export async function sendVoiceClientTelemetry(
  request: VoiceClientTelemetryRequest,
  options: VoiceClientOptions = {},
): Promise<VoiceClientResult<VoiceClientTelemetryPayload>> {
  const response = await postJson(
    VOICE_PATH,
    {
      ...request,
      action: 'client_telemetry',
    },
    options,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeClientTelemetryPayload(response, data),
  };
}

export async function interruptVoiceSession(
  request: VoiceInterruptRequest,
  options: VoiceClientOptions = {},
): Promise<VoiceClientResult<VoiceInterruptPayload>> {
  const response = await postJson(
    VOICE_PATH,
    {
      action: 'interrupt',
      sessionId: request.sessionId,
      language: request.language ?? 'ja',
    },
    options,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeInterruptPayload(response, data),
  };
}

export async function requestVoiceFiller(
  request: VoiceFillerRequest,
  options: VoiceClientOptions = {},
): Promise<VoiceClientResult<VoiceFillerPayload>> {
  const response = await postJson(
    VOICE_FILLER_PATH,
    {
      query: request.query,
      language: request.language,
      sessionId: request.sessionId,
    },
    options,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeFillerPayload(response, data),
  };
}

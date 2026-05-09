export type QaLanguage = 'ja' | 'en';
export type QaApiMode = 'proxy' | 'direct';

export interface QaRequest {
  readonly question: string;
  readonly text?: string;
  readonly sessionId: string;
  readonly language: QaLanguage;
  readonly visitorId?: string;
}

export interface QaResponsePayload {
  readonly success: boolean;
  readonly answer?: string;
  readonly emotion?: string;
  readonly metadata?: Record<string, unknown> | null;
  readonly vrm_control?: unknown;
  readonly error?: string;
}

export interface QaClientResult {
  readonly ok: boolean;
  readonly status: number;
  readonly data: QaResponsePayload;
  readonly mode: QaApiMode;
  readonly usedProxyFallback: boolean;
}

interface QaClientOptions {
  readonly signal?: AbortSignal;
}

const QA_PROXY_PATH = '/api/qa';
const DIRECT_CHAT_PATH = '/api/chat';

function getBackendBaseUrl(): string | null {
  const rawUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL?.trim();
  if (!rawUrl) {
    return null;
  }

  try {
    return new URL(rawUrl).toString().replace(/\/+$/, '');
  } catch {
    return null;
  }
}

export function getQaApiMode(): QaApiMode {
  if (process.env.NEXT_PUBLIC_QA_API_MODE !== 'direct') {
    return 'proxy';
  }

  return getBackendBaseUrl() ? 'direct' : 'proxy';
}

function directChatUrl(): string {
  const backendBaseUrl = getBackendBaseUrl();
  if (!backendBaseUrl) {
    throw new Error('NEXT_PUBLIC_BACKEND_API_URL is required for direct QA calls');
  }

  return `${backendBaseUrl}${DIRECT_CHAT_PATH}`;
}

function proxyBody(request: QaRequest): Record<string, unknown> {
  return {
    action: 'ask',
    question: request.question,
    text: request.text ?? request.question,
    sessionId: request.sessionId,
    language: request.language,
    visitorId: request.visitorId,
  };
}

function directBody(request: QaRequest): Record<string, unknown> {
  return {
    query: request.question || request.text || '',
    session_id: request.sessionId,
    language: request.language,
    visitor_id: request.visitorId,
  };
}

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

function normalizeProxyPayload(response: Response, data: Record<string, unknown>): QaResponsePayload {
  if (!response.ok) {
    return {
      success: false,
      error: errorMessage(data, '質問の送信に失敗しました'),
    };
  }

  return {
    ...data,
    success: data.success !== false,
  } as QaResponsePayload;
}

function normalizeDirectPayload(response: Response, data: Record<string, unknown>): QaResponsePayload {
  if (!response.ok) {
    return {
      success: false,
      error: errorMessage(data, '質問の送信に失敗しました'),
    };
  }

  const metadata =
    data.metadata && typeof data.metadata === 'object'
      ? (data.metadata as Record<string, unknown>)
      : null;

  return {
    success: true,
    answer: typeof data.answer === 'string' ? data.answer : '',
    emotion: typeof data.emotion === 'string' ? data.emotion : undefined,
    metadata,
    vrm_control: data.vrm_control ?? metadata?.vrm_control ?? null,
  };
}

async function postJson(
  url: string,
  body: Record<string, unknown>,
  signal: AbortSignal | undefined,
): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  });
}

async function submitViaProxy(
  request: QaRequest,
  options: QaClientOptions,
  usedProxyFallback: boolean,
): Promise<QaClientResult> {
  const response = await postJson(QA_PROXY_PATH, proxyBody(request), options.signal);
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeProxyPayload(response, data),
    mode: 'proxy',
    usedProxyFallback,
  };
}

function shouldFallbackToProxy(response: Response): boolean {
  return response.status === 401 || response.status === 403;
}

function isBrowserNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError;
}

export async function submitQaQuestion(
  request: QaRequest,
  options: QaClientOptions = {},
): Promise<QaClientResult> {
  if (getQaApiMode() === 'proxy') {
    return submitViaProxy(request, options, false);
  }

  try {
    const response = await postJson(directChatUrl(), directBody(request), options.signal);

    if (shouldFallbackToProxy(response)) {
      return submitViaProxy(request, options, true);
    }

    const data = await readJson(response);
    return {
      ok: response.ok,
      status: response.status,
      data: normalizeDirectPayload(response, data),
      mode: 'direct',
      usedProxyFallback: false,
    };
  } catch (error) {
    if (isBrowserNetworkFailure(error)) {
      return submitViaProxy(request, options, true);
    }

    throw error;
  }
}

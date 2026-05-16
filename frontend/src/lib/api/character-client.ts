export interface CharacterClientOptions {
  readonly signal?: AbortSignal;
}

export interface CharacterClientResult<TPayload> {
  readonly ok: boolean;
  readonly status: number;
  readonly data: TPayload;
}

export interface CharacterBasePayload {
  readonly success: boolean;
  readonly error?: string;
}

export interface CharacterAutoRequest {
  readonly cleanText: string;
  readonly emotion?: string | null;
  readonly ttsWavB64?: string;
}

export interface CharacterAutoPayload extends CharacterBasePayload {
  readonly vrmControl?: Record<string, unknown> | null;
}

export interface CharacterSupportedFeaturesPayload extends CharacterBasePayload {
  readonly expressions: string[];
  readonly animations: string[];
}

export interface CharacterStatusPayload {
  readonly status: string;
  readonly success: boolean;
  readonly error?: string;
}

const CHARACTER_PATH = '/api/character';

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

function optionalRecord(data: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const value = data[key];
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringArray(data: Record<string, unknown>, key: string): string[] {
  const value = data[key];
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string') ? value : [];
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

function normalizeAutoPayload(
  response: Response,
  data: Record<string, unknown>,
): CharacterAutoPayload {
  if (!response.ok) {
    return {
      success: false,
      error: errorMessage(data, 'キャラクター制御の生成に失敗しました'),
    };
  }

  return {
    success: data.success !== false,
    error: typeof data.error === 'string' ? data.error : undefined,
    vrmControl: optionalRecord(data, 'vrmControl'),
  };
}

function normalizeSupportedFeaturesPayload(
  response: Response,
  data: Record<string, unknown>,
): CharacterSupportedFeaturesPayload {
  if (!response.ok) {
    return {
      success: false,
      error: errorMessage(data, 'キャラクター機能の取得に失敗しました'),
      expressions: [],
      animations: [],
    };
  }

  return {
    success: data.success !== false,
    error: typeof data.error === 'string' ? data.error : undefined,
    expressions: stringArray(data, 'expressions'),
    animations: stringArray(data, 'animations'),
  };
}

function normalizeStatusPayload(
  response: Response,
  data: Record<string, unknown>,
): CharacterStatusPayload {
  if (!response.ok) {
    return {
      success: false,
      status: 'error',
      error: errorMessage(data, 'キャラクター状態の取得に失敗しました'),
    };
  }

  return {
    success: data.success !== false,
    status: typeof data.status === 'string' ? data.status : 'ok',
    error: typeof data.error === 'string' ? data.error : undefined,
  };
}

export async function requestAutoCharacterControl(
  request: CharacterAutoRequest,
  options: CharacterClientOptions = {},
): Promise<CharacterClientResult<CharacterAutoPayload>> {
  const response = await postJson(
    CHARACTER_PATH,
    {
      action: 'auto',
      cleanText: request.cleanText,
      emotion: request.emotion?.trim() || 'neutral',
      ...(typeof request.ttsWavB64 === 'string' && request.ttsWavB64.length > 0
        ? { ttsWavB64: request.ttsWavB64 }
        : {}),
    },
    options.signal,
  );
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeAutoPayload(response, data),
  };
}

export async function getCharacterSupportedFeatures(
  options: CharacterClientOptions = {},
): Promise<CharacterClientResult<CharacterSupportedFeaturesPayload>> {
  const response = await fetch(`${CHARACTER_PATH}?action=supported_features`, {
    signal: options.signal,
  });
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeSupportedFeaturesPayload(response, data),
  };
}

export async function getCharacterStatus(
  options: CharacterClientOptions = {},
): Promise<CharacterClientResult<CharacterStatusPayload>> {
  const response = await fetch(CHARACTER_PATH, {
    signal: options.signal,
  });
  const data = await readJson(response);

  return {
    ok: response.ok,
    status: response.status,
    data: normalizeStatusPayload(response, data),
  };
}

import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

const VOICE_PROXY_TIMEOUT_MS = 110_000;

function sanitizeTelemetryValue(value: unknown): unknown {
  if (typeof value === 'string') {
    return value.slice(0, 500);
  }
  if (
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    value === null ||
    value === undefined
  ) {
    return value;
  }
  return String(value).slice(0, 500);
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    // Validate required action field
    if (!body.action) {
      console.error('400 Error - Missing action field');
      return NextResponse.json({ error: 'Missing required field: action' }, { status: 400 });
    }

    const {
      action,
      audioData,
      sessionId,
      language,
      text,
      streaming,
      emotion,
      outputEncoding,
      ttsProvider,
      includeVrmControl,
    } = body as Record<string, unknown>;

    if (action === 'client_telemetry') {
      const telemetry = {
        event: sanitizeTelemetryValue(body.event),
        phase: sanitizeTelemetryValue(body.phase),
        sessionId: sanitizeTelemetryValue(body.sessionId),
        userAgent: sanitizeTelemetryValue(body.userAgent),
        errorName: sanitizeTelemetryValue(body.errorName),
        errorMessage: sanitizeTelemetryValue(body.errorMessage),
        deviceIdMode: sanitizeTelemetryValue(body.deviceIdMode),
        recorderState: sanitizeTelemetryValue(body.recorderState),
        retryWithDefaultDevice: sanitizeTelemetryValue(body.retryWithDefaultDevice),
        retryOutcome: sanitizeTelemetryValue(body.retryOutcome),
        retryErrorName: sanitizeTelemetryValue(body.retryErrorName),
        retryErrorMessage: sanitizeTelemetryValue(body.retryErrorMessage),
        timestamp: sanitizeTelemetryValue(body.timestamp),
      };
      console.warn('[VoiceClientTelemetry]', telemetry);
      return NextResponse.json({ success: true });
    }

    const response = await backendFetch('/api/voice', {
      body: {
        action,
        audioData,
        sessionId,
        language: (language as string) || 'ja',
        text,
        streaming: (streaming as boolean) || false,
        ...(typeof emotion === 'string' && emotion.length > 0 ? { emotion } : {}),
        ...(typeof outputEncoding === 'string' && outputEncoding.length > 0
          ? { outputEncoding }
          : {}),
        ...(typeof ttsProvider === 'string' && ttsProvider.length > 0 ? { ttsProvider } : {}),
        ...(includeVrmControl === true ? { includeVrmControl: true } : {}),
      },
      timeoutMs: VOICE_PROXY_TIMEOUT_MS,
    });

    if (!response.ok) {
      return createBackendErrorResponse(response);
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Voice API error:', error);
    return createInternalServerErrorResponse(error);
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action');

    const response = await backendFetch('/api/voice', {
      method: 'GET',
      params: action ? { action } : undefined,
      timeoutMs: VOICE_PROXY_TIMEOUT_MS,
    });

    if (!response.ok) {
      return createBackendErrorResponse(response);
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Voice API GET error:', error);
    return createInternalServerErrorResponse(error);
  }
}

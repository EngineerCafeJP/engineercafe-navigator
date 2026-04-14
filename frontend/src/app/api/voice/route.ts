import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

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
    } = body as Record<string, unknown>;

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
      },
      timeoutMs: 75_000,
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
      timeoutMs: 75_000,
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

import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';
import { fillerRequestSchema } from '@/lib/schemas/voice-filler';

const FILLER_PROXY_TIMEOUT_MS = 110_000;

export async function POST(request: NextRequest) {
  try {
    const raw = await request.json().catch(() => null);
    const parsed = fillerRequestSchema.safeParse(raw);
    if (!parsed.success) {
      return NextResponse.json(
        { error: 'INVALID_REQUEST', details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const { query, language } = parsed.data;

    const response = await backendFetch('/api/voice/filler', {
      body: { query, language },
      timeoutMs: FILLER_PROXY_TIMEOUT_MS,
    });

    if (!response.ok) {
      return createBackendErrorResponse(response);
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Voice filler API error:', error);
    return createInternalServerErrorResponse(error);
  }
}

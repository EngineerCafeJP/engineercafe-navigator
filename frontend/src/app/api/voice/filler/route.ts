import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

const FILLER_PROXY_TIMEOUT_MS = 15_000;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await backendFetch('/api/voice/filler', {
      body,
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

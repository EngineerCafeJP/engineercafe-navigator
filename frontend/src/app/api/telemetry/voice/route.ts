import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

const VOICE_TELEMETRY_PROXY_TIMEOUT_MS = 10_000;

function isTelemetryPayload(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null);

    if (!isTelemetryPayload(body)) {
      return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
    }

    const response = await backendFetch('/api/telemetry/voice', {
      body,
      timeoutMs: VOICE_TELEMETRY_PROXY_TIMEOUT_MS,
    });

    if (!response.ok) {
      return NextResponse.json({ success: true, proxied: false }, { status: 202 });
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Voice telemetry API error:', error);
    return NextResponse.json({ success: true, proxied: false }, { status: 202 });
  }
}

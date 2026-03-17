import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

type JsonValue = Record<string, unknown> | Array<unknown> | string | number | boolean | null;

function toHeaderRecord(headers?: HeadersInit): Record<string, string> {
  if (!headers) {
    return {};
  }

  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }

  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }

  return { ...headers };
}

function parseJsonBody(body: BodyInit | null | undefined): unknown {
  if (typeof body !== 'string') {
    return undefined;
  }

  try {
    return JSON.parse(body);
  } catch {
    return undefined;
  }
}

export async function proxyReceptionRequest(
  path: string,
  init: RequestInit
): Promise<NextResponse> {
  try {
    const response = await backendFetch<JsonValue>(path, {
      method: (init.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH') ?? 'POST',
      headers: toHeaderRecord(init.headers),
      body: parseJsonBody(init.body),
      signal: init.signal ?? undefined,
    });
    const data = response.data ?? null;

    if (!response.ok) {
      const message =
        data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
          ? data.error
          : `Backend API error: ${response.status}`;

      return NextResponse.json({ error: message }, { status: response.status });
    }

    return NextResponse.json(data ?? {});
  } catch (error) {
    console.error(`Reception proxy error for ${path}:`, error);

    return NextResponse.json(
      {
        error: 'Internal server error',
        ...(process.env.NODE_ENV === 'development' && {
          details: error instanceof Error ? error.message : 'Unknown error',
        }),
      },
      { status: 500 }
    );
  }
}

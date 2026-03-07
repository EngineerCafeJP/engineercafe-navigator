import { NextResponse } from 'next/server';

import { getBackendApiUrl } from '@/lib/api/backend-url';

type JsonValue = Record<string, unknown> | Array<unknown> | string | number | boolean | null;

async function readJson(response: Response): Promise<JsonValue | null> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    return null;
  }

  try {
    return (await response.json()) as JsonValue;
  } catch {
    return null;
  }
}

export async function proxyReceptionRequest(
  path: string,
  init: RequestInit
): Promise<NextResponse> {
  try {
    const response = await fetch(`${getBackendApiUrl()}${path}`, init);
    const data = await readJson(response);

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

import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

function toErrorBody(data: unknown, fallback: string) {
  if (data && typeof data === 'object') {
    const payload = data as {
      detail?: string;
      error?: string;
      message?: string;
    };
    const error = payload.error || payload.detail || payload.message;
    if (error) {
      return { ...payload, error };
    }
  }

  return { error: fallback };
}

export async function GET() {
  try {
    const response = await backendFetch('/api/knowledge/editor-config', {
      method: 'GET',
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to fetch knowledge editor config'),
        { status: response.status },
      );
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to get knowledge editor config' },
      { status: 500 },
    );
  }
}

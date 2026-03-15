import { NextRequest, NextResponse } from 'next/server';
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

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const params: Record<string, string> = {};

    searchParams.forEach((value, key) => {
      params[key] = value;
    });

    if (params.search && !params.keyword) {
      params.keyword = params.search;
    }

    const response = await backendFetch('/api/knowledge', {
      method: 'GET',
      params,
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to fetch knowledge entries'),
        { status: response.status }
      );
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to get knowledge entries' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await backendFetch('/api/knowledge', {
      method: 'POST',
      body: {
        title: body.title,
        content: body.content,
        category: body.category,
        subcategory: body.subcategory,
        language: body.language || 'ja',
        source: body.source || 'admin-ui',
        metadata: body.metadata || {},
      },
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to create entry'),
        { status: response.status }
      );
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to create knowledge entry' },
      { status: 500 }
    );
  }
}

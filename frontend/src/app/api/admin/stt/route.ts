import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

const ID_PATTERN = /^[a-zA-Z0-9_-]+$/;

function jsonResponse(data: unknown, status: number) {
  return NextResponse.json(data ?? null, { status });
}

function validateId(id: string | null): NextResponse | null {
  if (!id) {
    return NextResponse.json({ error: 'Missing id parameter' }, { status: 400 });
  }
  if (!ID_PATTERN.test(id)) {
    return NextResponse.json({ error: 'Invalid id format' }, { status: 400 });
  }
  return null;
}

const ALLOWED_PARAMS = new Set(['category', 'search', 'page', 'limit', 'language', 'offset']);

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');

    if (id) {
      const error = validateId(id);
      if (error) return error;

      const response = await backendFetch(`/api/stt/vocabulary/${id}`, {
        method: 'GET',
      });
      return jsonResponse(response.data, response.status);
    }

    const params: Record<string, string> = {};
    for (const [key, value] of searchParams.entries()) {
      if (ALLOWED_PARAMS.has(key)) {
        params[key] = value;
      }
    }

    const response = await backendFetch('/api/stt/vocabulary', {
      method: 'GET',
      params: Object.keys(params).length > 0 ? params : undefined,
    });

    return jsonResponse(response.data, response.status);
  } catch {
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await backendFetch('/api/stt/vocabulary', {
      method: 'POST',
      body,
    });

    return jsonResponse(response.data, response.status);
  } catch {
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 },
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    const error = validateId(id);
    if (error) return error;

    const body = await request.json();
    const response = await backendFetch(`/api/stt/vocabulary/${id}`, {
      method: 'PUT',
      body,
    });

    return jsonResponse(response.data, response.status);
  } catch {
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 },
    );
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    const error = validateId(id);
    if (error) return error;

    const response = await backendFetch(`/api/stt/vocabulary/${id}`, {
      method: 'DELETE',
    });

    return jsonResponse(response.data, response.status);
  } catch {
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 },
    );
  }
}

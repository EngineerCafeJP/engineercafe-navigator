import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

function jsonResponse(data: unknown, status: number) {
  return NextResponse.json(data ?? null, { status });
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    const params: Record<string, string> = {};

    for (const [key, value] of searchParams.entries()) {
      if (key !== 'id') {
        params[key] = value;
      }
    }

    const response = await backendFetch(
      id ? `/api/stt/vocabulary/${id}` : '/api/stt/vocabulary',
      {
        method: 'GET',
        params: Object.keys(params).length > 0 ? params : undefined,
      }
    );

    return jsonResponse(response.data, response.status);
  } catch (error) {
    console.error('STT vocabulary GET proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 }
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
  } catch (error) {
    console.error('STT vocabulary POST proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ error: 'Missing id parameter' }, { status: 400 });
    }

    const body = await request.json();
    const response = await backendFetch(`/api/stt/vocabulary/${id}`, {
      method: 'PUT',
      body,
    });

    return jsonResponse(response.data, response.status);
  } catch (error) {
    console.error('STT vocabulary PUT proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ error: 'Missing id parameter' }, { status: 400 });
    }

    const response = await backendFetch(`/api/stt/vocabulary/${id}`, {
      method: 'DELETE',
    });

    return jsonResponse(response.data, response.status);
  } catch (error) {
    console.error('STT vocabulary DELETE proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy STT vocabulary request' },
      { status: 500 }
    );
  }
}

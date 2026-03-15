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

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const response = await backendFetch(`/api/knowledge/${id}`, {
      method: 'GET',
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to fetch knowledge entry'),
        { status: response.status }
      );
    }

    const payload = response.data as { data?: unknown };
    return NextResponse.json(payload.data ?? payload, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to get knowledge entry' },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const response = await backendFetch(`/api/knowledge/${id}`, {
      method: 'PUT',
      body,
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to update knowledge entry'),
        { status: response.status }
      );
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to update knowledge entry' },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const response = await backendFetch(`/api/knowledge/${id}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      return NextResponse.json(
        toErrorBody(response.data, 'Failed to delete knowledge entry'),
        { status: response.status }
      );
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to delete knowledge entry' },
      { status: 500 }
    );
  }
}

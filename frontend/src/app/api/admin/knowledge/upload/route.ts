import { NextRequest, NextResponse } from 'next/server';

const BACKEND_API_URL = (process.env.BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

function backendUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${BACKEND_API_URL}${normalizedPath}`;
}

function backendHeaders(): HeadersInit {
  const apiKey = process.env.BACKEND_API_KEY || '';
  return apiKey ? { 'X-API-Key': apiKey } : {};
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const response = await fetch(backendUrl('/api/knowledge/upload'), {
      method: 'POST',
      headers: backendHeaders(),
      body: formData,
    });

    const text = await response.text();

    try {
      const json = text ? JSON.parse(text) : {};
      return NextResponse.json(json, { status: response.status });
    } catch {
      return NextResponse.json(
        { error: text || 'Failed to upload knowledge file' },
        { status: response.status },
      );
    }
  } catch {
    return NextResponse.json(
      { error: 'Failed to upload knowledge file' },
      { status: 500 },
    );
  }
}

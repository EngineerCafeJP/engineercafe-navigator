import { NextRequest, NextResponse } from 'next/server';

const BACKEND_API_URL = process.env.BACKEND_API_URL?.replace(/\/+$/, '') ?? '';
if (!BACKEND_API_URL) {
  console.warn('BACKEND_API_URL is not set. Template requests will fail.');
}
const ALLOWED_FILENAMES = new Set(['knowledge-template.md', 'knowledge-pdf-template-guide.md']);

function backendUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${BACKEND_API_URL}${normalizedPath}`;
}

function backendHeaders(): HeadersInit {
  const apiKey = process.env.BACKEND_API_KEY || '';
  return apiKey ? { 'X-API-Key': apiKey } : {};
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ filename: string }> },
) {
  try {
    const { filename } = await params;

    if (!ALLOWED_FILENAMES.has(filename)) {
      return NextResponse.json({ error: 'Template not found' }, { status: 404 });
    }

    const response = await fetch(
      backendUrl(`/api/knowledge/templates/${encodeURIComponent(filename)}`),
      {
        method: 'GET',
        headers: backendHeaders(),
      },
    );

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: text || 'Failed to download template' },
        { status: response.status },
      );
    }

    const headers = new Headers();
    headers.set('Content-Type', response.headers.get('Content-Type') || 'application/octet-stream');
    headers.set(
      'Content-Disposition',
      response.headers.get('Content-Disposition') || `attachment; filename="${filename}"`,
    );

    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers,
    });
  } catch {
    return NextResponse.json(
      { error: 'Failed to download template' },
      { status: 500 },
    );
  }
}

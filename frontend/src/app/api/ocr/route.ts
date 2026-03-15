import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.image_data) {
      return NextResponse.json(
        { error: 'Missing image_data field' },
        { status: 400 },
      );
    }

    const response = await backendFetch('/api/chat', {
      method: 'POST',
      body: {
        query: body.query || 'この画像を分析してください',
        session_id: body.session_id || '',
        language: body.language || 'ja',
        image_data: body.image_data,
      },
    });

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to process image' },
      { status: 500 },
    );
  }
}

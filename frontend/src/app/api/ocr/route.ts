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

    const response = await backendFetch('/api/ocr', {
      method: 'POST',
      body: {
        image_data: body.image_data,
        mode: body.mode || 'member_card',
        session_id: body.session_id || '',
      },
    });

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to process OCR' },
      { status: 500 },
    );
  }
}

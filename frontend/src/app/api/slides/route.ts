import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await backendFetch('/api/slides', {
      body,
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.status}`);
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Slides API error:', error);
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

export async function GET(request: NextRequest) {
  return NextResponse.json({
    status: 'ok',
    backend: 'connected',
  });
}

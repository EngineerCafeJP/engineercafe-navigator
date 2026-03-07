import { NextRequest, NextResponse } from 'next/server';
// TODO: Re-enable after backend migration is complete
// import { getEngineerCafeNavigator } from '@/mastra';
// import { Config } from '@/mastra/types/config';

import { getBackendApiUrl } from '@/lib/api/backend-url';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // バックエンドAPIにプロキシ
    const backendUrl = `${getBackendApiUrl()}/api/slides`;
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const result = await response.json();
    return NextResponse.json(result);
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

export async function OPTIONS(request: NextRequest) {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}

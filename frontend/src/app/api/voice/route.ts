import { NextRequest, NextResponse } from 'next/server';

import { getBackendApiUrl } from '@/lib/api/backend-url';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    // Validate required action field
    if (!body.action) {
      console.error('400 Error - Missing action field');
      return NextResponse.json({ error: 'Missing required field: action' }, { status: 400 });
    }

    const { action, audioData, sessionId, language, text, streaming } = body;

    // バックエンドAPIにプロキシ
    const backendUrl = `${getBackendApiUrl()}/api/voice`;
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        audioData,
        sessionId,
        language: language || 'ja',
        text,
        streaming: streaming || false,
      }),
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const result = await response.json();

    return NextResponse.json(result);
  } catch (error) {
    console.error('Voice API error:', error);
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
  try {
    const { searchParams } = new URL(request.url);
    const action = searchParams.get('action');

    // バックエンドAPIにプロキシ
    const backendUrl = `${getBackendApiUrl()}/api/voice?action=${action}`;
    const response = await fetch(backendUrl, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const result = await response.json();

    return NextResponse.json(result);
  } catch (error) {
    console.error('Voice API GET error:', error);
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

// Handle OPTIONS for CORS
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

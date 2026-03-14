import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    // Validate required action field
    if (!body.action) {
      console.error('400 Error - Missing action field');
      return NextResponse.json({ error: 'Missing required field: action' }, { status: 400 });
    }

    const { action, audioData, sessionId, language, text, streaming } = body;

    const response = await backendFetch('/api/voice', {
      body: {
        action,
        audioData,
        sessionId,
        language: language || 'ja',
        text,
        streaming: streaming || false,
      },
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.status}`);
    }

    return NextResponse.json(response.data);
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

    const response = await backendFetch('/api/voice', {
      method: 'GET',
      params: action ? { action } : undefined,
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.status}`);
    }

    return NextResponse.json(response.data);
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

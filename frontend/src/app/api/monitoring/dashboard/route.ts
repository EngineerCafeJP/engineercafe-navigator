import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const range = searchParams.get('range') || '24h';
    const response = await backendFetch('/api/monitoring/dashboard', {
      method: 'GET',
      params: { range },
    });

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json({ error: 'Failed to fetch dashboard' }, { status: 500 });
  }
}

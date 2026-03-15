import { NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

export async function GET() {
  try {
    const response = await backendFetch('/api/monitoring/migration-success', {
      method: 'GET',
    });

    return NextResponse.json(response.data, { status: response.status });
  } catch {
    return NextResponse.json({ error: 'Failed to fetch migration status' }, { status: 500 });
  }
}

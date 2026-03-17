import { NextResponse } from 'next/server';
import { backendFetch } from '@/lib/api/backend-proxy';

export async function GET() {
  try {
    const response = await backendFetch('/api/knowledge/categories', {
      method: 'GET',
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: 'Failed to fetch categories' },
        { status: response.status },
      );
    }

    return NextResponse.json(response.data, { status: 200 });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch knowledge categories' },
      { status: 500 },
    );
  }
}

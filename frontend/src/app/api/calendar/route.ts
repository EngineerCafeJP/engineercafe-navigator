import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

export async function GET(_request: NextRequest) {
  try {
    const response = await backendFetch('/api/calendar', {
      method: 'GET',
    });

    if (!response.ok) {
      return createBackendErrorResponse(response, 'Failed to fetch calendar data');
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch (error) {
    console.error('Calendar API error:', error);
    return createInternalServerErrorResponse(error, 'Failed to fetch calendar data');
  }
}

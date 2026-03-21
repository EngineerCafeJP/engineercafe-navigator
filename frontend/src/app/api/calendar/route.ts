import { NextRequest, NextResponse } from 'next/server';

import {
  createBackendErrorResponse,
  createInternalServerErrorResponse,
} from '@/app/api/_shared/backend-error-response';
import { backendFetch } from '@/lib/api/backend-proxy';

export async function GET(request: NextRequest) {
  try {
    const timeRange = request.nextUrl.searchParams.get('timeRange');
    const params: Record<string, string> = {};
    if (timeRange) {
      params.timeRange = timeRange;
    }

    const response = await backendFetch('/api/calendar', {
      method: 'GET',
      params,
    });

    if (!response.ok) {
      return createBackendErrorResponse(response, 'Failed to fetch calendar data');
    }

    return NextResponse.json(response.data, { status: response.status });
  } catch (error) {
    return createInternalServerErrorResponse(error, 'Failed to fetch calendar data');
  }
}

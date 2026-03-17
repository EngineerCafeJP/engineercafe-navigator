import { NextResponse } from 'next/server';

import type { BackendProxyResult } from '@/lib/api/backend-proxy';

type ErrorBody = {
  error: string;
  details?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function includeDetails(details?: string): Pick<ErrorBody, 'details'> | Record<string, never> {
  if (process.env.NODE_ENV !== 'development' || !details) {
    return {};
  }

  return { details };
}

function normalizeBackendError(data: unknown, fallbackError: string): ErrorBody {
  if (typeof data === 'string' && data.trim()) {
    return { error: data };
  }

  if (!isRecord(data)) {
    return { error: fallbackError };
  }

  const error =
    typeof data.error === 'string'
      ? data.error
      : typeof data.detail === 'string'
        ? data.detail
        : typeof data.message === 'string'
          ? data.message
          : fallbackError;

  const details =
    typeof data.details === 'string'
      ? data.details
      : typeof data.error === 'string' && typeof data.detail === 'string'
        ? data.detail
        : undefined;

  return {
    error,
    ...includeDetails(details),
  };
}

export function createBackendErrorResponse(
  response: Pick<BackendProxyResult<unknown>, 'status' | 'data'>,
  fallbackError = `Backend API error: ${response.status}`
) {
  return NextResponse.json(normalizeBackendError(response.data, fallbackError), {
    status: response.status,
  });
}

export function createInternalServerErrorResponse(
  error: unknown,
  fallbackError = 'Internal server error'
) {
  return NextResponse.json(
    {
      error: fallbackError,
      ...includeDetails(error instanceof Error ? error.message : 'Unknown error'),
    },
    { status: 500 }
  );
}

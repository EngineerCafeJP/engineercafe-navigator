import { NextRequest } from 'next/server';

import { proxyReceptionRequest } from '../../_shared';

interface RouteContext {
  params: Promise<{
    receptionSessionId: string;
  }>;
}

export async function GET(request: NextRequest, context: RouteContext) {
  const { receptionSessionId } = await context.params;
  const sessionId = request.nextUrl.searchParams.get('session_id');

  const search = sessionId
    ? `?${new URLSearchParams({ session_id: sessionId }).toString()}`
    : '';

  return proxyReceptionRequest(`/api/reception/status/${receptionSessionId}${search}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

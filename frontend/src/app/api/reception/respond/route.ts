import { NextRequest } from 'next/server';

import { proxyReceptionRequest } from '../_shared';

export async function POST(request: NextRequest) {
  const body = await request.json();

  return proxyReceptionRequest('/api/reception/respond', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

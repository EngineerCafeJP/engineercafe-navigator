import { NextRequest } from 'next/server';

import { proxyReceptionRequest } from '../_shared';

export async function GET(request: NextRequest) {
  const deviceId = request.nextUrl.searchParams.get('device_id') ?? 'm5stack-001';
  const since = request.nextUrl.searchParams.get('since') ?? '0';
  const search = new URLSearchParams({
    device_id: deviceId,
    since,
  }).toString();

  return proxyReceptionRequest(`/api/reception/sensor-status?${search}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
}

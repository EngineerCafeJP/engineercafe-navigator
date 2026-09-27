import { NextRequest, NextResponse } from 'next/server';

import { isMaintenanceMode } from './lib/maintenance-mode';
import { maintenanceResponse } from './lib/maintenance-response';

function unauthorizedResponse(): NextResponse {
  return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
}

async function timingSafeEqualStr(a: string, b: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const aHash = await crypto.subtle.digest('SHA-256', encoder.encode(a));
  const bHash = await crypto.subtle.digest('SHA-256', encoder.encode(b));
  const aArr = new Uint8Array(aHash);
  const bArr = new Uint8Array(bHash);
  let result = 0;

  for (let i = 0; i < aArr.byteLength; i += 1) {
    result |= aArr[i] ^ bArr[i];
  }

  return result === 0;
}

function isAdminRoute(pathname: string): boolean {
  return pathname.startsWith('/api/admin/') || pathname === '/api/admin';
}

function isProtectedOperationalRoute(pathname: string): boolean {
  return (
    isAdminRoute(pathname) ||
    pathname.startsWith('/api/cron/') ||
    pathname === '/api/cron' ||
    pathname.startsWith('/api/monitoring/') ||
    pathname === '/api/monitoring'
  );
}

function shouldTraceUserAgent(pathname: string): boolean {
  return (
    pathname === '/api/voice' ||
    pathname === '/api/qa' ||
    pathname === '/api/character' ||
    pathname === '/api/slides' ||
    pathname.startsWith('/api/reception/')
  );
}

function traceUserAgent(request: NextRequest): void {
  if (!shouldTraceUserAgent(request.nextUrl.pathname)) {
    return;
  }

  const ua = request.headers.get('user-agent') ?? 'unknown';
  console.log(
    `[ua-trace] ${request.method} ${request.nextUrl.pathname} ua=${JSON.stringify(ua)}`
  );
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // Read both variables by name so Next.js exposes them to the middleware bundle.
  const maintenance = isMaintenanceMode({
    MAINTENANCE_MODE: process.env.MAINTENANCE_MODE,
    VERCEL_ENV: process.env.VERCEL_ENV,
  });

  if (maintenance) {
    return maintenanceResponse(request.nextUrl.pathname);
  }

  traceUserAgent(request);

  if (!isProtectedOperationalRoute(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const adminApiSecret = process.env.ADMIN_API_SECRET?.trim();

  if (!adminApiSecret) {
    if (isAdminRoute(request.nextUrl.pathname) || process.env.NODE_ENV === 'production') {
      return unauthorizedResponse();
    }

    return NextResponse.next();
  }

  const authHeader = request.headers.get('authorization');
  const expected = `Bearer ${adminApiSecret}`;

  if (!authHeader || !(await timingSafeEqualStr(authHeader, expected))) {
    return unauthorizedResponse();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Every path, so maintenance mode can answer pages and APIs alike. Next.js
    // assets are skipped, and /api/alerts/webhook keeps bypassing the middleware
    // because it verifies its own secret instead of the admin bearer token.
    '/((?!_next/static|_next/image|favicon.ico|api/alerts/webhook).*)',
  ],
};

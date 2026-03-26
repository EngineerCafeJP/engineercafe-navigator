import { NextRequest, NextResponse } from 'next/server';

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

/**
 * Detect same-origin browser requests via the Sec-Fetch-Site header.
 * Modern browsers set this automatically; non-browser clients (curl, etc.)
 * do not send it. This header cannot be spoofed by browser-side JavaScript.
 */
function isSameOriginBrowserRequest(request: NextRequest): boolean {
  return request.headers.get('sec-fetch-site') === 'same-origin';
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // Allow same-origin browser requests to admin routes without Bearer token.
  // The underlying API routes still enforce backend auth via X-API-Key.
  if (isAdminRoute(request.nextUrl.pathname) && isSameOriginBrowserRequest(request)) {
    return NextResponse.next();
  }

  const adminApiSecret = process.env.ADMIN_API_SECRET?.trim();

  if (!adminApiSecret) {
    if (process.env.NODE_ENV === 'production') {
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
    '/api/admin/:path*',
    '/api/cron/:path*',
    '/api/monitoring/:path*',
  ],
};

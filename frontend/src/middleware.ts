import crypto from 'crypto';
import { NextRequest, NextResponse } from 'next/server';

function unauthorizedResponse(): NextResponse {
  return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
}

function timingSafeEqualStr(a: string, b: string): boolean {
  const aBuf = Buffer.from(a);
  const bBuf = Buffer.from(b);
  if (aBuf.length !== bBuf.length) return false;
  return crypto.timingSafeEqual(aBuf, bBuf);
}

export function middleware(request: NextRequest): NextResponse {
  const adminApiSecret = process.env.ADMIN_API_SECRET;

  if (!adminApiSecret) {
    if (process.env.NODE_ENV === 'production') {
      return unauthorizedResponse();
    }

    console.warn(
      `ADMIN_API_SECRET is not set; allowing ${request.nextUrl.pathname} in non-production mode.`,
    );
    return NextResponse.next();
  }

  const authHeader = request.headers.get('authorization');
  const expected = `Bearer ${adminApiSecret}`;

  if (!authHeader || !timingSafeEqualStr(authHeader, expected)) {
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

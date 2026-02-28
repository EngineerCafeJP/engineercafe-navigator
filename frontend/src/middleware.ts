import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const adminSecret = process.env.ADMIN_SECRET_KEY

  // If ADMIN_SECRET_KEY is not set, allow all access (development mode)
  if (!adminSecret) {
    return NextResponse.next()
  }

  const { pathname } = request.nextUrl

  // Skip login page and auth API
  if (pathname === '/admin/login' || pathname.startsWith('/api/admin/auth')) {
    return NextResponse.next()
  }

  const token = request.cookies.get('admin-token')?.value

  // API routes: return 401 JSON
  if (pathname.startsWith('/api/admin')) {
    if (!token || token !== adminSecret) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }
    return NextResponse.next()
  }

  // Admin pages: redirect to login
  if (!token || token !== adminSecret) {
    const loginUrl = new URL('/admin/login', request.url)
    loginUrl.searchParams.set('from', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/admin/:path*', '/api/admin/:path*'],
}

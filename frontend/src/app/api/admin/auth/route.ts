import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'

export async function POST(request: Request) {
  const adminSecret = process.env.ADMIN_SECRET_KEY

  if (!adminSecret) {
    return NextResponse.json(
      { error: 'ADMIN_SECRET_KEY not configured' },
      { status: 500 }
    )
  }

  const body = await request.json()
  const { password } = body

  if (!password || password !== adminSecret) {
    return NextResponse.json(
      { error: 'Invalid password' },
      { status: 401 }
    )
  }

  const cookieStore = await cookies()
  cookieStore.set('admin-token', adminSecret, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24, // 24 hours
  })

  return NextResponse.json({ success: true })
}

export async function DELETE() {
  const cookieStore = await cookies()
  cookieStore.delete('admin-token')
  return NextResponse.json({ success: true })
}

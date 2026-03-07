import { NextRequest, NextResponse } from 'next/server';

// NOTE: This route is actively called by MarpViewer.tsx (frontend/src/app/components/MarpViewer.tsx)
// for Marp markdown slide rendering. Do not remove.
// TODO: Re-enable after backend migration is complete
// import { getEngineerCafeNavigator } from '@/mastra';
// import { Config } from '@/mastra/types/config';

export async function POST(request: NextRequest) {
  return NextResponse.json({
    success: false,
    error: 'Marp API temporarily disabled during backend migration',
  }, { status: 503 });
}

export async function GET() {
  return NextResponse.json({
    status: 'migrating',
    message: 'Marp API temporarily disabled during backend migration',
  });
}

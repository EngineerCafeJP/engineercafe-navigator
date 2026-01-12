import { NextRequest, NextResponse } from 'next/server';
// TODO: Re-enable after backend migration is complete
// import { getEngineerCafeNavigator } from '@/mastra';
// import { Config } from '@/mastra/types/config';

export async function POST(request: NextRequest) {
  return NextResponse.json({
    success: false,
    error: 'External API temporarily disabled during backend migration',
  }, { status: 503 });
}

export async function GET() {
  return NextResponse.json({
    status: 'migrating',
    message: 'External API temporarily disabled during backend migration',
  });
}

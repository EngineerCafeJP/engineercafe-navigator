import { NextRequest, NextResponse } from 'next/server';
// TODO: Re-enable after backend migration is complete
// import { MarpRendererTool } from '@/mastra/tools/marp-renderer';

export async function POST(request: NextRequest) {
  return NextResponse.json({
    success: false,
    error: 'Marp test API temporarily disabled during backend migration',
  }, { status: 503 });
}

export async function GET(request: NextRequest) {
  return NextResponse.json({
    status: 'migrating',
    message: 'Marp test API temporarily disabled during backend migration',
  });
}

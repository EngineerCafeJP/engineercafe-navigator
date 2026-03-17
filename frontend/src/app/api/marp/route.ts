import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';
import { MarpProcessor } from '@/lib/marp-processor';

let marpProcessor: MarpProcessor | null = null;

function getMarpProcessor(): MarpProcessor {
  if (!marpProcessor) {
    marpProcessor = new MarpProcessor();
  }
  return marpProcessor;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const language = body.language || 'ja';

    const backendResponse = await backendFetch<{
      success?: boolean;
      markdown?: string;
      error?: string;
      metadata?: {
        title?: string;
      };
      narrationData?: unknown;
    }>('/api/slides/content', {
      body: { language },
    });

    if (!backendResponse.ok) {
      throw new Error(`Backend error: ${backendResponse.status}`);
    }

    const backendData = backendResponse.data;
    if (!backendData.success || !backendData.markdown) {
      throw new Error(backendData.error || 'No markdown content returned');
    }

    const processed = getMarpProcessor().processMarkdown(backendData.markdown);
    const title =
      backendData.metadata?.title || processed.metadata.title || 'Presentation';

    const escapedTitle = MarpProcessor.escapeHtml(title);
    const sanitizedCss = MarpProcessor.sanitizeCss(processed.css);

    const fullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapedTitle}</title>
  <style>${sanitizedCss}</style>
</head>
<body>
  ${processed.html}
</body>
</html>`;

    return NextResponse.json({
      success: true,
      html: fullHtml,
      slideData: {
        slides: processed.slides,
      },
      narrationData: backendData.narrationData,
      slideCount: processed.slides.length,
      metadata: backendData.metadata,
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to render slides',
        ...(process.env.NODE_ENV === 'development' && {
          details: error instanceof Error ? error.message : 'Unknown error',
        }),
      },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    backend: 'connected',
  });
}

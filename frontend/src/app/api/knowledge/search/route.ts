import { NextRequest, NextResponse } from 'next/server';
// TODO: Re-enable after backend migration is complete
// import { ragSearchTool } from '@/mastra/tools/rag-search';
import { z } from 'zod';

// Request validation schema
const searchRequestSchema = z.object({
  query: z.string().min(1, 'Query is required'),
  language: z.enum(['ja', 'en']).optional(),
  category: z.string().optional(),
  limit: z.number().min(1).max(10).optional(),
  threshold: z.number().min(0).max(1).optional(),
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate request
    const validationResult = searchRequestSchema.safeParse(body);
    if (!validationResult.success) {
      return NextResponse.json(
        {
          error: 'Invalid request',
          details: validationResult.error.errors,
        },
        { status: 400 }
      );
    }

    // TODO: Implement backend proxy after migration
    return NextResponse.json({
      success: false,
      error: 'Knowledge search temporarily disabled during backend migration',
      results: [],
      count: 0,
    }, { status: 503 });

    // const { query, language, category, limit, threshold } = validationResult.data;
    // Perform RAG search
    // const searchResult = await ragSearchTool.execute({
    //   query,
    //   language,
    //   category,
    //   limit: limit || 5,
    //   threshold: threshold || 0.7,
    // });

    // if (!searchResult.success) {
    //   return NextResponse.json(
    //     {
    //       error: 'Search failed',
    //       message: searchResult.message,
    //     },
    //     { status: 500 }
    //   );
    // }

    // return NextResponse.json({
    //   success: true,
    //   results: searchResult.results,
    //   count: searchResult.results.length,
    //   message: searchResult.message,
    // });
  } catch (error) {
    console.error('Knowledge search error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

// GET endpoint to check if the knowledge base is populated
export async function GET() {
  return NextResponse.json({
    status: 'migrating',
    hasData: false,
    message: 'Knowledge base API temporarily disabled during backend migration',
  });
}

import { NextRequest, NextResponse } from 'next/server';
import { knowledgeBaseUpdater } from '@/jobs/update-knowledge-base';
import { dispatchCronAlert } from '@/lib/monitoring/cron-alerts';
import { ragMetrics } from '@/lib/monitoring/rag-metrics';

const CRON_NAME = '/api/cron/update-knowledge-base';
const CRON_ROUTE_TIMEOUT_MS = 290_000;

function createTimeoutError(timeoutMs: number): Error {
  return new Error(`Knowledge base update timed out after ${timeoutMs}ms`);
}

async function runKnowledgeBaseUpdateWithTimeout({
  timeoutMs,
}: {
  timeoutMs: number;
}): Promise<void> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  const updatePromise = knowledgeBaseUpdater.runUpdate();

  updatePromise.catch((error) => {
    if (timedOut) {
      console.error('[CRON] Knowledge base update failed after route timeout:', error);
    }
  });

  try {
    await Promise.race([
      updatePromise,
      new Promise<never>((_, reject) => {
        timeoutId = setTimeout(() => {
          timedOut = true;
          reject(createTimeoutError(timeoutMs));
        }, timeoutMs);
        timeoutId.unref?.();
      }),
    ]);
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

/**
 * CRON endpoint for automated knowledge base updates
 * This endpoint is called by Vercel CRON or external schedulers
 */
export async function GET(request: NextRequest) {
  // Verify the request is from Vercel CRON
  const authHeader = request.headers.get('authorization');
  
  if (process.env.NODE_ENV === 'production') {
    // In production, verify the CRON secret
    const cronSecret = process.env.CRON_SECRET;
    if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }
  }
  
  const startTime = Date.now();
  
  try {
    // Run the update
    await runKnowledgeBaseUpdateWithTimeout({ timeoutMs: CRON_ROUTE_TIMEOUT_MS });
    
    const duration = Date.now() - startTime;
    
    // Track metrics
    await ragMetrics.trackKnowledgeBaseOperation({
      operation: 'batch_import',
      category: 'automated_update',
      count: 1,
      duration,
      success: true,
    });
    
    return NextResponse.json({
      success: true,
      message: 'Knowledge base update completed',
      duration: `${duration}ms`,
      timestamp: new Date().toISOString(),
    });
    
  } catch (error) {
    const duration = Date.now() - startTime;
    const cronError = error instanceof Error ? error : new Error('Unknown error');
    let metricsTracked = false;
    
    console.error('[CRON] Knowledge base update failed:', error);
    
    // Track error metrics
    try {
      await ragMetrics.trackKnowledgeBaseOperation({
        operation: 'batch_import',
        category: 'automated_update',
        count: 0,
        duration,
        success: false,
        error: cronError.message,
      });
      metricsTracked = true;
    } catch (metricsError) {
      console.error('[CRON] Failed to track knowledge base error metrics:', metricsError);
    }

    await dispatchCronAlert({
      cronName: CRON_NAME,
      startTime,
      duration,
      error: cronError,
      metricsTracked,
    });
    
    return NextResponse.json(
      {
        error: 'Knowledge base update failed',
        message: cronError.message,
        duration: `${duration}ms`,
        timestamp: new Date().toISOString(),
      },
      { status: 500 }
    );
  }
}

/**
 * Manual trigger endpoint (for testing)
 */
export async function POST(request: NextRequest) {
  // This endpoint can be used to manually trigger updates during development
  if (process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { error: 'Manual triggers not allowed in production' },
      { status: 403 }
    );
  }
  
  return GET(request);
}

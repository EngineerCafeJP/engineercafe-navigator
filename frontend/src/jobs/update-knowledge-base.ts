import 'server-only';
import { CronJob } from 'cron';
import { connpassClient } from '../lib/external-apis/connpass-client';
import { supabaseAdmin } from '../lib/supabase';
import { v4 as uuidv4 } from 'uuid';

const CONNPASS_KNOWLEDGE_CATEGORY = 'event';
const OPENROUTER_EMBEDDING_URL = 'https://openrouter.ai/api/v1/embeddings';
const OPENROUTER_EMBEDDING_MODEL = 'openai/text-embedding-3-small';
const OPENROUTER_EMBEDDING_DIMENSIONS = 1536;
const OPENROUTER_EMBEDDING_TIMEOUT_MS = 15_000;
const KNOWLEDGE_BASE_UPDATE_CRON_JST = '30 4 * * *';
const KNOWLEDGE_BASE_UPDATE_LOCK_METRIC_TYPE = 'knowledge_base_update_lock';
const KNOWLEDGE_BASE_UPDATE_LOCK_TTL_MS = 20 * 60 * 1000;

type ConnpassClient = typeof connpassClient;
type SupabaseAdmin = typeof supabaseAdmin;
type UpdateLease = {
  acquired: boolean;
  distributed: boolean;
  ownerId: string;
  expiresAt: string;
};
type MetricRow = {
  created_at?: string;
  metadata?: unknown;
};

interface KnowledgeBaseUpdaterDependencies {
  connpassClient?: ConnpassClient;
  supabaseAdmin?: SupabaseAdmin;
  fetch?: typeof fetch;
  getOpenRouterApiKey?: () => string | undefined;
}

/**
 * Automated knowledge base updater that syncs external data sources
 *
 * Server-only cron helper. Direct service-role access remains intentional until
 * this workflow is fully owned by the backend.
 */
export class KnowledgeBaseUpdater {
  private job: CronJob;
  private isRunning = false;
  private readonly connpassClient: ConnpassClient;
  private readonly supabaseAdmin: SupabaseAdmin;
  private readonly fetchImpl: typeof fetch;
  private readonly getOpenRouterApiKey: () => string | undefined;
  
  constructor(dependencies: KnowledgeBaseUpdaterDependencies = {}) {
    this.connpassClient = dependencies.connpassClient ?? connpassClient;
    this.supabaseAdmin = dependencies.supabaseAdmin ?? supabaseAdmin;
    this.fetchImpl = dependencies.fetch ?? fetch;
    this.getOpenRouterApiKey = dependencies.getOpenRouterApiKey ?? (() => process.env.OPENROUTER_API_KEY);

    // Mirrors Vercel's 19:30 UTC cron, which is 04:30 JST and outside kiosk business hours.
    this.job = new CronJob(KNOWLEDGE_BASE_UPDATE_CRON_JST, async () => {
      try {
        await this.runUpdate();
      } catch (error) {
        console.error('[KnowledgeBaseUpdater] Scheduled update failed:', error);
      }
    }, null, false, 'Asia/Tokyo');
  }
  
  /**
   * Start the cron job
   */
  start() {
    this.job.start();
  }
  
  /**
   * Stop the cron job
   */
  stop() {
    this.job.stop();
  }
  
  /**
   * Run update immediately (can be called manually)
   */
  async runUpdate(): Promise<void> {
    if (this.isRunning) {
      return;
    }
    
    this.isRunning = true;
    const startTime = Date.now();
    let lease: UpdateLease | undefined;
    
    try {
      lease = await this.acquireUpdateLease();
      if (!lease.acquired) {
        console.warn('[KnowledgeBaseUpdater] Update skipped because another instance holds the lease');
        return;
      }
      
      // Run all updates in parallel
      const results = await Promise.allSettled([
        this.updateFromConnpass(),
        this.updateFromGoogleCalendar(),
        this.updateFromWebsite(),
      ]);
      
      // Log results
      results.forEach((result, index) => {
        const source = ['Connpass', 'Google Calendar', 'Website'][index];
        if (result.status === 'rejected') {
          console.error(`[KnowledgeBaseUpdater] ${source} update failed:`, result.reason);
        }
      });
      
      // Clean up old entries
      await this.cleanupOldEntries();
      
      const duration = Date.now() - startTime;
      
      // Track metrics before surfacing required-source failures to the cron route.
      await this.trackUpdateMetrics({
        duration,
        sources: {
          connpass: results[0].status === 'fulfilled',
          googleCalendar: results[1].status === 'fulfilled' && results[1].value !== 'Skipped - handled by backend',
          website: results[2].status === 'fulfilled',
        },
      });

      if (results[0].status === 'rejected') {
        throw new Error(
          `Required knowledge base source Connpass failed: ${this.getErrorMessage(results[0].reason)}`
        );
      }
      
    } catch (error) {
      console.error('[KnowledgeBaseUpdater] Update failed:', error);
      throw error;
    } finally {
      if (lease?.acquired) {
        await this.releaseUpdateLease(lease);
      }
      this.isRunning = false;
    }
  }
  
  /**
   * Update knowledge base from Connpass events
   */
  private async updateFromConnpass(): Promise<string> {
    try {
      const openRouterApiKey = this.getOpenRouterApiKey()?.trim();
      if (!openRouterApiKey) {
        const message = [
          '[updateFromConnpass] OPENROUTER_API_KEY is not set;',
          'cannot update Connpass events because embeddings are required.',
        ].join(' ');
        console.error(message);
        throw new Error(message);
      }

      // Search for Engineer Cafe events
      const events = await this.connpassClient.searchEngineerCafeEvents({
        includeEnded: false,
        count: 50,
      });
      
      let added = 0;
      let updated = 0;
      let skipped = 0;
      let failed = 0;
      
      for (const event of events) {
        const content = this.formatConnpassEvent(event);
        let contentEmbedding: number[];

        try {
          contentEmbedding = await this.generateEmbedding(content, openRouterApiKey);
        } catch (error) {
          skipped++;
          console.error(
            `[updateFromConnpass] Skipping event ${event.event_id}; embedding generation failed:`,
            error
          );
          continue;
        }

        const knowledgeEntry = {
          title: event.title,
          content,
          content_embedding: contentEmbedding,
          category: CONNPASS_KNOWLEDGE_CATEGORY,
          subcategory: 'connpass',
          source: 'connpass',
          language: this.detectLanguage(event.title + ' ' + event.description),
          metadata: {
            source: 'connpass',
            event_id: event.event_id,
            event_url: event.event_url,
            start_date: event.started_at,
            end_date: event.ended_at,
            place: event.place,
            updated_at: event.updated_at,
            embedding_model: OPENROUTER_EMBEDDING_MODEL,
            embedding_dimensions: OPENROUTER_EMBEDDING_DIMENSIONS,
            embedding_generated_at: new Date().toISOString(),
          },
        };
        
        // Check if event already exists
        const { data: existing } = await this.supabaseAdmin
          .from('knowledge_base')
          .select('id')
          .eq('metadata->>event_id', event.event_id.toString())
          .single();
        
        if (existing) {
          // Update existing entry
          const { error } = await this.supabaseAdmin
            .from('knowledge_base')
            .update({
              ...knowledgeEntry,
              updated_at: new Date().toISOString(),
            })
            .eq('id', existing.id);
          
          if (error) {
            failed++;
            console.error(`[updateFromConnpass] Failed to update event ${event.event_id}:`, error);
          } else {
            updated++;
          }
        } else {
          // Add new entry
          const { error } = await this.supabaseAdmin
            .from('knowledge_base')
            .insert({
              id: uuidv4(),
              ...knowledgeEntry,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            });
          
          if (error) {
            failed++;
            console.error(`[updateFromConnpass] Failed to insert event ${event.event_id}:`, error);
          } else {
            added++;
          }
        }
      }
      
      return this.formatConnpassUpdateResult({ added, updated, skipped, failed });
    } catch (error) {
      console.error('[updateFromConnpass] Error:', error);
      throw error;
    }
  }
  
  /**
   * Update knowledge base from Google Calendar
   */
  private async updateFromGoogleCalendar(): Promise<string> {
    return 'Skipped - handled by backend';
  }
  
  /**
   * Update knowledge base from website scraping
   */
  private async updateFromWebsite(): Promise<string> {
    // For now, return a placeholder
    // In production, this would scrape the Engineer Cafe website
    // using tools like Puppeteer or Playwright
    return 'Website scraping not yet implemented';
  }
  
  /**
   * Format Connpass event for knowledge base
   */
  private formatConnpassEvent(event: any): string {
    const currentJST = this.getCurrentJSTTime();
    const eventStatus = this.getEventStatusForKnowledge({
      start: event.started_at,
      end: event.ended_at
    });
    
    const parts = [
      `イベント名: ${event.title}`,
      eventStatus ? `状態: ${eventStatus}` : '',
      `キャッチコピー: ${event.catch}`,
      `開催日時: ${this.formatDateTime(event.started_at)} - ${this.formatDateTime(event.ended_at)}`,
      `場所: ${event.place}`,
      event.address ? `住所: ${event.address}` : '',
      `定員: ${event.limit || '制限なし'}`,
      `参加者: ${event.accepted}名`,
      event.waiting > 0 ? `キャンセル待ち: ${event.waiting}名` : '',
      `詳細: ${event.description.substring(0, 500)}...`,
      `URL: ${event.event_url}`,
      `情報取得時刻: ${currentJST}`,
    ].filter(Boolean);
    
    return parts.join('\n');
  }
  
  /**
   * Format datetime string
   */
  private formatDateTime(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  private async generateEmbedding(text: string, apiKey: string): Promise<number[]> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), OPENROUTER_EMBEDDING_TIMEOUT_MS);
    timeoutId.unref?.();

    let response: Response;
    try {
      response = await this.fetchImpl(OPENROUTER_EMBEDDING_URL, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: OPENROUTER_EMBEDDING_MODEL,
          input: text,
          dimensions: OPENROUTER_EMBEDDING_DIMENSIONS,
        }),
      });
    } catch (error) {
      if (this.isAbortLikeError(error)) {
        throw new Error(`OpenRouter embedding request timed out after ${OPENROUTER_EMBEDDING_TIMEOUT_MS}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }

    if (!response.ok) {
      const details = await response.text().catch(() => '');
      throw new Error(`OpenRouter embedding API error: ${response.status}${details ? ` ${details}` : ''}`);
    }

    const data = await response.json() as { data?: Array<{ embedding?: unknown }> };
    const embedding = data.data?.[0]?.embedding;

    if (
      !Array.isArray(embedding) ||
      embedding.length !== OPENROUTER_EMBEDDING_DIMENSIONS ||
      !embedding.every((value) => typeof value === 'number')
    ) {
      throw new Error(`Invalid embedding shape; expected ${OPENROUTER_EMBEDDING_DIMENSIONS} numeric dimensions`);
    }

    return embedding;
  }

  private async acquireUpdateLease(): Promise<UpdateLease> {
    const ownerId = uuidv4();
    const now = Date.now();
    const expiresAt = new Date(now + KNOWLEDGE_BASE_UPDATE_LOCK_TTL_MS).toISOString();

    if (process.env.NODE_ENV !== 'production') {
      return { acquired: true, distributed: false, ownerId, expiresAt };
    }

    try {
      const activeSince = new Date(now - KNOWLEDGE_BASE_UPDATE_LOCK_TTL_MS).toISOString();
      const activeRows = await this.readRecentUpdateLeaseRows(activeSince);
      const activeLease = this.findActiveUpdateLease(activeRows, now);

      if (activeLease) {
        return { acquired: false, distributed: true, ownerId, expiresAt };
      }

      await this.insertUpdateLeaseMetric({
        ownerId,
        status: 'running',
        value: 1,
        expiresAt,
      });

      const contenderRows = await this.readRecentUpdateLeaseRows(activeSince);
      const contenders = this.activeUpdateLeaseContenders(contenderRows, now);
      const winner = contenders[0];
      if (winner && winner.ownerId !== ownerId) {
        await this.insertUpdateLeaseMetric({
          ownerId,
          status: 'skipped',
          value: 0,
          expiresAt,
        });
        return { acquired: false, distributed: true, ownerId, expiresAt };
      }

      return { acquired: true, distributed: true, ownerId, expiresAt };
    } catch (error) {
      console.warn(
        '[KnowledgeBaseUpdater] Distributed update lease unavailable; falling back to process-local guard:',
        error
      );
      return { acquired: true, distributed: false, ownerId, expiresAt };
    }
  }

  private async releaseUpdateLease(lease: UpdateLease): Promise<void> {
    if (!lease.distributed) {
      return;
    }

    try {
      await this.insertUpdateLeaseMetric({
        ownerId: lease.ownerId,
        status: 'completed',
        value: 0,
        expiresAt: lease.expiresAt,
      });
    } catch (error) {
      console.warn('[KnowledgeBaseUpdater] Failed to release distributed update lease:', error);
    }
  }

  private async readRecentUpdateLeaseRows(activeSince: string): Promise<MetricRow[]> {
    const query = (this.supabaseAdmin as any)
      .from('system_metrics')
      .select('created_at, metadata')
      .eq('metric_type', KNOWLEDGE_BASE_UPDATE_LOCK_METRIC_TYPE)
      .gte('created_at', activeSince)
      .order('created_at', { ascending: true })
      .limit(50);
    const { data, error } = await query;

    if (error) {
      throw error;
    }

    return Array.isArray(data) ? data : [];
  }

  private async insertUpdateLeaseMetric(input: {
    ownerId: string;
    status: 'running' | 'completed' | 'skipped';
    value: number;
    expiresAt: string;
  }): Promise<void> {
    const { error } = await (this.supabaseAdmin as any)
      .from('system_metrics')
      .insert({
        metric_type: KNOWLEDGE_BASE_UPDATE_LOCK_METRIC_TYPE,
        value: input.value,
        metadata: {
          owner_id: input.ownerId,
          status: input.status,
          expires_at: input.expiresAt,
          lock_ttl_ms: KNOWLEDGE_BASE_UPDATE_LOCK_TTL_MS,
        },
        created_at: new Date().toISOString(),
      });

    if (error) {
      throw error;
    }
  }

  private findActiveUpdateLease(rows: MetricRow[], now: number): { ownerId: string } | null {
    return this.activeUpdateLeaseContenders(rows, now)[0] ?? null;
  }

  private activeUpdateLeaseContenders(rows: MetricRow[], now: number): Array<{
    acquiredAt: string;
    ownerId: string;
  }> {
    const releasedOwners = new Set<string>();

    for (const row of rows) {
      const metadata = this.metricMetadata(row.metadata);
      if (
        metadata?.owner_id &&
        (metadata.status === 'completed' || metadata.status === 'skipped')
      ) {
        releasedOwners.add(metadata.owner_id);
      }
    }

    return rows
      .map((row) => {
        const metadata = this.metricMetadata(row.metadata);
        return {
          acquiredAt: row.created_at ?? '',
          ownerId: metadata?.owner_id ?? '',
          status: metadata?.status,
          expiresAt: metadata?.expires_at,
        };
      })
      .filter((row) => {
        if (!row.ownerId || row.status !== 'running' || releasedOwners.has(row.ownerId)) {
          return false;
        }
        return row.expiresAt ? Date.parse(row.expiresAt) > now : false;
      })
      .sort((a, b) => {
        const timeDiff = Date.parse(a.acquiredAt) - Date.parse(b.acquiredAt);
        return timeDiff === 0 ? a.ownerId.localeCompare(b.ownerId) : timeDiff;
      })
      .map((row) => ({ acquiredAt: row.acquiredAt, ownerId: row.ownerId }));
  }

  private metricMetadata(metadata: unknown): {
    owner_id?: string;
    status?: string;
    expires_at?: string;
  } | null {
    if (!metadata || typeof metadata !== 'object') {
      return null;
    }

    return metadata as {
      owner_id?: string;
      status?: string;
      expires_at?: string;
    };
  }

  private isAbortLikeError(error: unknown): boolean {
    if (!(error instanceof Error || error instanceof DOMException)) {
      return false;
    }

    return error.name === 'AbortError' || error.name === 'TimeoutError';
  }

  private formatConnpassUpdateResult(result: {
    added: number;
    updated: number;
    skipped: number;
    failed: number;
  }): string {
    return [
      `Added ${result.added}, updated ${result.updated}, skipped ${result.skipped}, failed ${result.failed} events`,
      "Existing Connpass rows with category 'events' still need a one-time migration to category 'event'.",
    ].join('. ');
  }

  private getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
  
  /**
   * Simple language detection
   */
  private detectLanguage(text: string): 'ja' | 'en' {
    // Check for Japanese characters
    const hasJapanese = /[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf\u3400-\u4dbf]/.test(text);
    return hasJapanese ? 'ja' : 'en';
  }
  
  /**
   * Clean up old entries
   */
  private async cleanupOldEntries(): Promise<void> {
    // Remove events that ended more than 30 days ago
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    
    await this.supabaseAdmin
      .from('knowledge_base')
      .delete()
      .in('category', [CONNPASS_KNOWLEDGE_CATEGORY, 'events'])
      .lt('metadata->>end_date', thirtyDaysAgo.toISOString());
  }
  
  /**
   * Track update metrics
   */
  private async trackUpdateMetrics(metrics: {
    duration: number;
    sources: {
      connpass: boolean;
      googleCalendar: boolean;
      website: boolean;
    };
  }): Promise<void> {
    try {
      await this.supabaseAdmin
        .from('system_metrics')
        .insert({
          metric_type: 'knowledge_base_update',
          value: metrics.duration,
          metadata: metrics.sources,
          created_at: new Date().toISOString(),
        });
    } catch (error) {
      console.error('[trackUpdateMetrics] Error:', error);
    }
  }
  
  /**
   * Get current JST time string
   */
  private getCurrentJSTTime(): string {
    const now = new Date();
    // Convert to JST (UTC+9)
    const jstOffset = 9 * 60; // JST is UTC+9
    const localOffset = now.getTimezoneOffset();
    const jstTime = new Date(now.getTime() + (jstOffset + localOffset) * 60 * 1000);
    
    const year = jstTime.getFullYear();
    const month = jstTime.getMonth() + 1;
    const day = jstTime.getDate();
    const hour = jstTime.getHours();
    const minute = jstTime.getMinutes();
    
    const dayOfWeek = ['日', '月', '火', '水', '木', '金', '土'][jstTime.getDay()];
    
    return `${year}年${month}月${day}日(${dayOfWeek}) ${hour}:${minute.toString().padStart(2, '0')} JST`;
  }
  
  /**
   * Get event status for knowledge base
   */
  private getEventStatusForKnowledge(event: any): string | null {
    const now = new Date();
    const start = new Date(event.start);
    const end = new Date(event.end);
    
    // Check if event is happening now
    if (start <= now && now <= end) {
      return '現在開催中';
    }
    
    // Check if event is today
    const todayStart = new Date(now);
    todayStart.setHours(0, 0, 0, 0);
    const todayEnd = new Date(todayStart);
    todayEnd.setDate(todayEnd.getDate() + 1);
    
    if (start >= todayStart && start < todayEnd) {
      if (start > now) {
        return '本日開催予定';
      }
    }
    
    // Check if event is tomorrow
    const tomorrowStart = new Date(todayEnd);
    const tomorrowEnd = new Date(tomorrowStart);
    tomorrowEnd.setDate(tomorrowEnd.getDate() + 1);
    
    if (start >= tomorrowStart && start < tomorrowEnd) {
      return '明日開催予定';
    }
    
    // Check if event is this week
    const weekEnd = new Date(now);
    weekEnd.setDate(weekEnd.getDate() + (7 - weekEnd.getDay())); // End of week (Saturday)
    weekEnd.setHours(23, 59, 59, 999);
    
    if (start <= weekEnd) {
      return '今週開催予定';
    }
    
    return null;
  }
}

// Export singleton instance
export const knowledgeBaseUpdater = new KnowledgeBaseUpdater();

/**
 * Temporary type definitions for migrated Mastra types
 * TODO: These should eventually be imported from backend API types
 */

export type SupportedLanguage = 'ja' | 'en';

export interface KnowledgeSearchResult {
  id: string;
  content: string;
  metadata: Record<string, any>;
  similarity?: number;
  category?: string;
}

export class RAGSearchTool {
  async execute(options: { query: string; language?: string; limit?: number; threshold?: number }): Promise<{ success: boolean; results: KnowledgeSearchResult[] }> {
    // TODO: Implement backend proxy after migration
    console.warn('[RAGSearchTool] Temporarily disabled during migration');
    return { success: false, results: [] };
  }
}

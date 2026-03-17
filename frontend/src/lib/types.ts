/**
 * Shared frontend type definitions
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

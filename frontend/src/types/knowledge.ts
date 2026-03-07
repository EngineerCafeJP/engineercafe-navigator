/**
 * Knowledge Base API Types
 */

export interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  category?: string;
  subcategory?: string;
  language: string;
  source?: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface KnowledgeListResponse {
  success: boolean;
  data: KnowledgeItem[];
  total: number;
  page: number;
  limit: number;
}

export interface KnowledgeResponse {
  success: boolean;
  data: KnowledgeItem;
  error?: string;
}

export interface KnowledgeEditorConfig {
  categories: string[];
  subcategories: Record<string, string[]>;
  sources: string[];
  languages: string[];
  stats: {
    totalCategories: number;
    totalSubcategories: number;
    totalSources: number;
    totalLanguages: number;
  };
  templates: Record<string, Record<string, any>>;
  available_categories: string[];
}

export interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  category?: string;
  subcategory?: string;
  language: string;
  source?: string;
  metadata?: Record<string, unknown>;
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

export interface KnowledgeCategoriesResponse {
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
}

export interface KnowledgeEditorConfig extends KnowledgeCategoriesResponse {
  templates: Record<string, Record<string, unknown>>;
  availableCategories: string[];
}

export interface MetadataFieldConfig {
  type: 'select' | 'date' | 'tags' | 'text';
  options?: string[];
}

export const METADATA_FIELD_TYPES = {
  importance: { type: 'select', options: ['critical', 'high', 'medium', 'low'] },
  last_updated: { type: 'date' },
  tags: { type: 'tags' },
  title: { type: 'text' },
  source: { type: 'text' },
  category: { type: 'text' },
  slideNumber: { type: 'text' },
  original_file: { type: 'text' },
} as const satisfies Record<string, MetadataFieldConfig>;

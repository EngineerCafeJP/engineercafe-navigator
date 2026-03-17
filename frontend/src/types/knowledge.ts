<<<<<<< HEAD
/**
 * Knowledge Base API Types
 */

=======
>>>>>>> origin/develop
export interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  category?: string;
  subcategory?: string;
  language: string;
  source?: string;
<<<<<<< HEAD
  metadata?: Record<string, any>;
=======
  metadata?: Record<string, unknown>;
>>>>>>> origin/develop
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

<<<<<<< HEAD
export interface KnowledgeEditorConfig {
=======
export interface KnowledgeCategoriesResponse {
>>>>>>> origin/develop
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
<<<<<<< HEAD
  templates: Record<string, Record<string, any>>;
  available_categories: string[];
}
=======
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
>>>>>>> origin/develop

<<<<<<< HEAD
/**
 * Knowledge Base API Client
 * FastAPI に直接アクセスする API クライアント関数
 */

import {
  type KnowledgeItem,
  type KnowledgeListResponse,
  type KnowledgeResponse,
  type KnowledgeEditorConfig,
} from '@/types/knowledge';

// Re-export for backward compatibility
export type { KnowledgeItem, KnowledgeListResponse, KnowledgeResponse, KnowledgeEditorConfig };

// ============================================================================
// API URL Helper
// ============================================================================

function getKnowledgeBackendUrl(): string {
  const url = process.env.NEXT_PUBLIC_BACKEND_API_URL;
  if (url) return url;
  if (process.env.NODE_ENV === "development") return "http://localhost:8000/api";
  throw new Error("NEXT_PUBLIC_BACKEND_API_URL environment variable is required");
}

function getBackendUrl(): string {
  return getKnowledgeBackendUrl();
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * ナレッジ一覧取得（フィルタ・ページネーション対応）
 * SWR キーは params オブジェクト、fetcher として使用
 *
 * 使用例：
 * const { data } = useSWR({ search, category, language, page }, getKnowledgeList);
 */
=======
import {
  type KnowledgeCategoriesResponse,
  type KnowledgeEditorConfig,
  type KnowledgeItem,
  type KnowledgeListResponse,
  type KnowledgeResponse,
} from '@/types/knowledge';

export type {
  KnowledgeCategoriesResponse,
  KnowledgeEditorConfig,
  KnowledgeItem,
  KnowledgeListResponse,
  KnowledgeResponse,
};

interface KnowledgeTemplatesResponse {
  templates: Record<string, Record<string, unknown>>;
  availableCategories: string[];
}

interface KnowledgeMutationPayload {
  title: string;
  content: string;
  category: string;
  language: string;
  subcategory?: string;
  source?: string;
  metadata?: Record<string, unknown>;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      searchParams.set(key, String(value));
    }
  });

  const query = searchParams.toString();
  return query ? `?${query}` : '';
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const text = await response.text();
  if (!text) {
    return fallback;
  }

  try {
    const data = JSON.parse(text) as {
      detail?: string;
      error?: string;
      message?: string;
    };
    return data.error || data.detail || data.message || fallback;
  } catch {
    return text;
  }
}

>>>>>>> origin/develop
export async function getKnowledgeList(params: {
  search?: string;
  category?: string;
  language?: string;
  page?: number;
  limit?: number;
}): Promise<KnowledgeListResponse> {
<<<<<<< HEAD
  const query = new URLSearchParams();
  if (params.search) query.set("keyword", params.search); // フロント: search → バック: keyword
  if (params.category) query.set("category", params.category);
  if (params.language) query.set("language", params.language);
  query.set("page", String(params.page ?? 1));
  query.set("limit", String(params.limit ?? 20));

  const url = `${getBackendUrl()}/knowledge?${query.toString()}`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch knowledge: ${res.status}`);
  return res.json();
}

/**
 * ナレッジ単一取得
 */
export async function getKnowledgeById(id: string): Promise<KnowledgeItem> {
  const url = `${getBackendUrl()}/knowledge/${id}`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch knowledge: ${res.status}`);
  const json = await res.json();
  return json.data; // FastAPI は { success, data: KnowledgeItem } 形式なので data を unwrap
}

/**
 * ナレッジ新規作成
 */
export async function createKnowledge(body: {
  title: string;
  content: string;
  category: string;
  language: string;
  subcategory?: string;
  source?: string;
  metadata?: Record<string, any>;
}): Promise<KnowledgeItem> {
  const url = `${getBackendUrl()}/knowledge`;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to create knowledge: ${res.status} - ${errorText}`);
  }

  const json = await res.json();
  return json.data; // FastAPI は { success, data: KnowledgeItem } 形式なので data を unwrap
}

/**
 * ナレッジ更新
 */
export async function updateKnowledge(
  id: string,
  body: Partial<{
    title: string;
    content: string;
    category: string;
    language: string;
    subcategory: string;
    source: string;
    metadata: Record<string, any>;
  }>
): Promise<KnowledgeItem> {
  const url = `${getBackendUrl()}/knowledge/${id}`;

  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to update knowledge: ${res.status} - ${errorText}`);
  }

  const json = await res.json();
  return json.data; // FastAPI は { success, data: KnowledgeItem } 形式なので data を unwrap
}

/**
 * ナレッジ削除
 */
export async function deleteKnowledge(id: string): Promise<void> {
  const url = `${getBackendUrl()}/knowledge/${id}`;

  const res = await fetch(url, {
    method: "DELETE",
  });

  if (!res.ok) throw new Error(`Failed to delete knowledge: ${res.status}`);
}

/**
 * ファイルアップロード
 * category と language は必須、title は任意
 */
=======
  const response = await fetch(
    `/api/admin/knowledge${buildQuery({
      search: params.search,
      category: params.category,
      language: params.language,
      page: params.page ?? 1,
      limit: params.limit ?? 20,
    })}`,
  );

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to fetch knowledge entries'));
  }

  return response.json();
}

export async function getKnowledgeById(id: string): Promise<KnowledgeItem> {
  const response = await fetch(`/api/admin/knowledge/${id}`);

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to fetch knowledge entry'));
  }

  return response.json();
}

export async function createKnowledge(body: KnowledgeMutationPayload): Promise<KnowledgeItem> {
  const response = await fetch('/api/admin/knowledge', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to create knowledge entry'));
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function updateKnowledge(
  id: string,
  body: Partial<KnowledgeMutationPayload>,
): Promise<KnowledgeItem> {
  const response = await fetch(`/api/admin/knowledge/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to update knowledge entry'));
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function deleteKnowledge(id: string): Promise<void> {
  const response = await fetch(`/api/admin/knowledge/${id}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to delete knowledge entry'));
  }
}

>>>>>>> origin/develop
export async function uploadKnowledgeFile(params: {
  file: File;
  category: string;
  language: string;
  title?: string;
}): Promise<KnowledgeItem> {
<<<<<<< HEAD
  const url = `${getBackendUrl()}/knowledge/upload`;

  const formData = new FormData();
  formData.append("file", params.file);
  formData.append("category", params.category);
  formData.append("language", params.language);
  if (params.title) {
    formData.append("title", params.title);
  }

  const res = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to upload knowledge file: ${res.status} - ${errorText}`);
  }

  const json = await res.json();
  return json.data; // FastAPI は { success, data: KnowledgeItem } 形式なので data を unwrap
}

/**
 * エディタ設定データ取得（カテゴリ、テンプレート等）
 */
export async function getKnowledgeEditorConfig(): Promise<KnowledgeEditorConfig> {
  const url = `${getBackendUrl()}/knowledge/editor-config`;

  const res = await fetch(url);
  if (!res.ok)
    throw new Error(`Failed to fetch editor config: ${res.status}`);
  return res.json();
=======
  const formData = new FormData();
  formData.append('file', params.file);
  formData.append('category', params.category);
  formData.append('language', params.language);
  if (params.title) {
    formData.append('title', params.title);
  }

  const response = await fetch('/api/admin/knowledge/upload', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to upload knowledge file'));
  }

  const json = (await response.json()) as KnowledgeResponse | KnowledgeItem;
  return 'data' in json ? json.data : json;
}

export async function getKnowledgeEditorConfig(): Promise<KnowledgeEditorConfig> {
  const [categoriesResponse, templatesResponse] = await Promise.all([
    fetch('/api/admin/knowledge/categories'),
    fetch('/api/admin/knowledge/metadata-templates'),
  ]);

  if (!categoriesResponse.ok) {
    throw new Error(await getErrorMessage(categoriesResponse, 'Failed to fetch categories'));
  }

  if (!templatesResponse.ok) {
    throw new Error(await getErrorMessage(templatesResponse, 'Failed to fetch metadata templates'));
  }

  const categories = (await categoriesResponse.json()) as KnowledgeCategoriesResponse;
  const templates = (await templatesResponse.json()) as KnowledgeTemplatesResponse;

  return {
    ...categories,
    templates: templates.templates,
    availableCategories: templates.availableCategories,
  };
}

export async function downloadTemplate(params: {
  filename: string;
  timestamp: number;
}): Promise<Blob> {
  const response = await fetch(
    `/api/admin/knowledge/templates/${encodeURIComponent(params.filename)}${buildQuery({
      t: params.timestamp,
    })}`,
  );

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to download template'));
  }

  return response.blob();
>>>>>>> origin/develop
}

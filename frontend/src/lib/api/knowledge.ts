/**
 * Knowledge Base API Client
 * FastAPI に直接アクセスする API クライアント関数
 */

// ============================================================================
// Types
// ============================================================================

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
export async function getKnowledgeList(params: {
  search?: string;
  category?: string;
  language?: string;
  page?: number;
  limit?: number;
}): Promise<KnowledgeListResponse> {
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

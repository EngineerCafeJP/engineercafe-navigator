/**
 * STT Vocabulary API Client
 * Admin proxy 経由で STT vocabulary API にアクセスするクライアント関数
 */

import { VocabularyItem, VocabularyListResponse } from "@/types/vosk";

// ============================================================================
// API クライアント
// ============================================================================

/**
 * 語彙一覧取得（URL生成とfetchを統合）
 * SWR キーは params オブジェクト、fetcher として使用
 *
 * page.tsx での使用例：
 * const { data } = useSWR({ category, search, page, limit }, getVocabularyList);
 */
export async function getVocabularyList(params: {
  category?: string;
  search?: string;
  page?: number;
  limit?: number;
}): Promise<VocabularyListResponse> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.search) query.set("search", params.search);
  query.set("page", String(params.page ?? 1));
  query.set("limit", String(params.limit ?? 20));
  const url = `/api/admin/stt?${query.toString()}`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch vocabulary: ${res.status}`);
  return res.json();
}

/**
 * 語彙削除
 */
export async function deleteVocabulary(id: string): Promise<void> {
  const res = await fetch(`/api/admin/stt?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete vocabulary: ${res.status}`);
}

/**
 * 語彙詳細取得（編集時に既存データを取得）
 */
export async function getVocabularyDetail(id: string): Promise<VocabularyItem> {
  const res = await fetch(`/api/admin/stt?id=${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`Failed to fetch vocabulary detail: ${res.status}`);
  const json = await res.json();
  return json.data;
}

/**
 * 語彙作成
 */
export async function createVocabulary(data: {
  word: string;
  reading: string;
  category: string;
  priority: number;
}): Promise<VocabularyItem> {
  const res = await fetch("/api/admin/stt", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || `Failed to create vocabulary: ${res.status}`);
  }
  const json = await res.json();
  return json.data;
}

/**
 * 語彙更新
 */
export async function updateVocabulary(
  id: string,
  data: {
    word: string;
    reading: string;
    category: string;
    priority: number;
  }
): Promise<VocabularyItem> {
  const res = await fetch(`/api/admin/stt?id=${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || `Failed to update vocabulary: ${res.status}`);
  }
  const json = await res.json();
  return json.data;
}

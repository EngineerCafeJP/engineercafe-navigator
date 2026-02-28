/**
 * STT Vocabulary API Client
 * FastAPI に直接アクセスする API クライアント関数
 */

import { VocabularyListResponse } from "@/types/vosk";

// ============================================================================
// API クライアント
// ============================================================================

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_API_URL ?? "http://localhost:8000/api";

// 開発環境で未設定の場合に警告
if (
  process.env.NODE_ENV === "development" &&
  !process.env.NEXT_PUBLIC_BACKEND_API_URL
) {
  console.warn(
    "[stt-vocabulary] NEXT_PUBLIC_BACKEND_API_URL is not set. " +
      "Falling back to http://localhost:8000/api. " +
      "Add it to frontend/.env.local to suppress this warning.",
  );
}

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
  const url = `${BACKEND_URL}/stt/vocabulary?${query.toString()}`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch vocabulary: ${res.status}`);
  return res.json();
}

/**
 * 語彙削除
 */
export async function deleteVocabulary(id: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/stt/vocabulary/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete vocabulary: ${res.status}`);
}

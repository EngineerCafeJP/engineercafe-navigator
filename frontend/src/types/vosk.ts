/**
 * Vosk Vocabulary Types & Constants
 */

export type VocabularyCategory =
  | "facility"      // 施設
  | "location"      // 場所
  | "service"       // サービス
  | "event"         // イベント
  | "person"        // 人名
  | "tech"          // 技術用語
  | "organization"; // 組織・団体

export interface VocabularyItem {
  id: string;
  word: string;
  reading: string;
  category: VocabularyCategory;
  priority: number;     // 1-10
  created_at: string;   // ISO 8601
  updated_at: string;   // ISO 8601
}

export interface VocabularyStats {
  total: number;
  byCategory: Record<VocabularyCategory, number>;
}

export interface VocabularyListResponse {
  success: boolean;
  data: VocabularyItem[];
  total: number;
  page: number;
  limit: number;
  stats: VocabularyStats;
}

export const CATEGORY_METADATA: Record<
  VocabularyCategory,
  { label: string; badgeClass: string }
> = {
  facility: { label: "施設", badgeClass: "bg-blue-100 text-blue-800" },
  location: { label: "場所", badgeClass: "bg-green-100 text-green-800" },
  service: { label: "サービス", badgeClass: "bg-purple-100 text-purple-800" },
  event: { label: "イベント", badgeClass: "bg-orange-100 text-orange-800" },
  person: { label: "人名", badgeClass: "bg-pink-100 text-pink-800" },
  tech: { label: "技術用語", badgeClass: "bg-cyan-100 text-cyan-800" },
  organization: {
    label: "組織・団体",
    badgeClass: "bg-yellow-100 text-yellow-800",
  },
};

export const CATEGORY_ORDER = [
  "facility",
  "location",
  "service",
  "event",
  "person",
  "tech",
  "organization",
] as const;

"use client";

import {
  VocabularyCategory,
  CATEGORY_METADATA,
  CATEGORY_ORDER,
} from "@/types/vosk";

interface VoskVocabularyFilterProps {
  searchInput: string;
  categoryFilter: VocabularyCategory | "";
  onSearchInputChange: (value: string) => void;
  onCategoryChange: (value: VocabularyCategory | "") => void;
  onSearch: (e: React.FormEvent) => void;
}

export function VoskVocabularyFilter({
  searchInput,
  categoryFilter,
  onSearchInputChange,
  onCategoryChange,
  onSearch,
}: VoskVocabularyFilterProps) {
  return (
    <form onSubmit={onSearch} className="flex gap-3 mb-6">
      <input
        type="text"
        placeholder="検索（単語または読み仮名）"
        value={searchInput}
        onChange={(e) => onSearchInputChange(e.target.value)}
        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
      />
      <select
        value={categoryFilter}
        onChange={(e) => onCategoryChange(e.target.value as VocabularyCategory | "")}
        className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 bg-white"
      >
        <option value="">すべて</option>
        {CATEGORY_ORDER.map((cat) => (
          <option key={cat} value={cat}>
            {CATEGORY_METADATA[cat].label}
          </option>
        ))}
      </select>
      <button
        type="submit"
        className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg"
      >
        検索
      </button>
    </form>
  );
}

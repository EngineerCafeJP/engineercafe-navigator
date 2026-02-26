"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import { Toaster, toast } from "react-hot-toast";
import {
  VocabularyItem,
  VocabularyListResponse,
  VocabularyCategory,
} from "@/types/vosk";
import {
  getVocabularyList,
  deleteVocabulary,
} from "@/lib/api/stt-vocabulary";
import { DeleteConfirmModal } from "./components/DeleteConfirmModal";
import { VoskVocabularyFilter } from "./components/VoskVocabularyFilter";
import { VoskVocabularyStats } from "./components/VoskVocabularyStats";
import { VoskVocabularyTable } from "./components/VoskVocabularyTable";

const ITEMS_PER_PAGE = 20;

export default function VoskSettingsPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<VocabularyCategory | "">(
    ""
  );
  const [deletingItem, setDeletingItem] = useState<VocabularyItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // SWR キーとパラメータを生成
  const swrKey = useMemo(
    () => ({
      category: categoryFilter || undefined,
      search: appliedSearch || undefined,
      page,
      limit: ITEMS_PER_PAGE,
    }),
    [categoryFilter, appliedSearch, page]
  );

  // SWR でデータを取得
  const { data, error, isLoading, mutate } = useSWR<VocabularyListResponse>(
    swrKey,
    getVocabularyList
  );

  const vocabularyData = data?.data ?? [];
  const stats = data?.stats ?? null;
  const totalFiltered = data?.total ?? 0;

  // 検索実行
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setAppliedSearch(searchInput);
    setPage(1);
  };

  // カテゴリフィルター変更
  const handleCategoryChange = (cat: VocabularyCategory | "") => {
    setCategoryFilter(cat);
    setPage(1);
  };

  // 削除確認
  const handleDeleteConfirm = async () => {
    if (!deletingItem) return;
    setIsDeleting(true);
    try {
      await deleteVocabulary(deletingItem.id);
      toast.success("削除しました");
      setDeletingItem(null);
      mutate();
    } catch {
      toast.error("削除に失敗しました");
    } finally {
      setIsDeleting(false);
    }
  };

  // モーダルキャンセル処理
  const handleDeleteCancel = useCallback(() => {
    setDeletingItem(null);
  }, []);

  const hasFilter = !!(categoryFilter || appliedSearch);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Toaster position="top-right" />

      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          {/* Header */}
          <div className="border-b border-gray-200 p-6 flex justify-between items-center">
            <h1 className="text-2xl font-bold text-gray-900">
              音声認識語彙管理
            </h1>
            <div className="flex gap-3">
              <button
                disabled
                title="この機能は準備中です"
                className="px-4 py-2 bg-blue-300 cursor-not-allowed opacity-60 text-white font-medium rounded-lg"
              >
                + 新規追加
              </button>
              <button
                disabled
                title="この機能は準備中です"
                className="px-4 py-2 bg-green-300 cursor-not-allowed opacity-60 text-white font-medium rounded-lg"
              >
                インポート
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* Error Message */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-700 text-sm">
                  データの取得に失敗しました。バックエンドが起動しているか確認してください。
                </p>
              </div>
            )}

            {/* Filter Bar */}
            <VoskVocabularyFilter
              searchInput={searchInput}
              categoryFilter={categoryFilter}
              onSearchInputChange={setSearchInput}
              onCategoryChange={handleCategoryChange}
              onSearch={handleSearch}
            />

            {/* Main Content Area */}
            <div className="flex gap-6">
              {/* Left: Table */}
              <div className="flex-1 min-w-0">
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600" />
                  </div>
                ) : (
                  <VoskVocabularyTable
                    items={vocabularyData}
                    totalItems={totalFiltered}
                    page={page}
                    itemsPerPage={ITEMS_PER_PAGE}
                    onPageChange={setPage}
                    onDeleteClick={setDeletingItem}
                    hasFilter={hasFilter}
                  />
                )}
              </div>

              {/* Right: Statistics */}
              <div className="w-64 flex-shrink-0">
                <VoskVocabularyStats stats={stats} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deletingItem && (
        <DeleteConfirmModal
          item={deletingItem}
          isDeleting={isDeleting}
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
        />
      )}
    </div>
  );
}

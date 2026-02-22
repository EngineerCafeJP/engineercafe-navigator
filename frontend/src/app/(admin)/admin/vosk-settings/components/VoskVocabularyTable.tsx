"use client";

import { VocabularyItem, CATEGORY_METADATA } from "@/types/vosk";
import { isoConvertDate } from "@/utils/iso-convert-date";

interface VoskVocabularyTableProps {
  items: VocabularyItem[];
  totalItems: number;
  page: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  onDeleteClick: (item: VocabularyItem) => void;
  hasFilter: boolean;
}

export function VoskVocabularyTable({
  items,
  totalItems,
  page,
  itemsPerPage,
  onPageChange,
  onDeleteClick,
  hasFilter,
}: VoskVocabularyTableProps) {
  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">
          {hasFilter
            ? "条件に一致する語彙が見つかりませんでした"
            : "登録されている語彙がありません"}
        </p>
      </div>
    );
  }

  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const startItem = (page - 1) * itemsPerPage + 1;
  const endItem = Math.min(page * itemsPerPage, totalItems);

  return (
    <div className="space-y-4">
      {/* Table */}
      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                単語
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                読み仮名
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                カテゴリ
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                更新日時
              </th>
              <th className="px-6 py-3 text-center text-sm font-semibold text-gray-900">
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.id}
                className="border-b border-gray-200 hover:bg-gray-50"
              >
                <td className="px-6 py-3 text-sm text-gray-900">{item.word}</td>
                <td className="px-6 py-3 text-sm text-gray-600">{item.reading}</td>
                <td className="px-6 py-3 text-sm">
                  <span
                    className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                      CATEGORY_METADATA[item.category].badgeClass
                    }`}
                  >
                    {CATEGORY_METADATA[item.category].label}
                  </span>
                </td>
                <td className="px-6 py-3 text-sm text-gray-600">
                  {isoConvertDate(item.updated_at)}
                </td>
                <td className="px-6 py-3 text-sm text-center space-x-2">
                  <button
                    disabled
                    title="この機能は準備中です"
                    className="text-gray-400 cursor-not-allowed font-medium"
                  >
                    編集
                  </button>
                  <button
                    onClick={() => onDeleteClick(item)}
                    className="text-red-600 hover:text-red-900 font-medium"
                  >
                    削除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600">
          全{totalItems}件中 {startItem}-{endItem}件を表示
        </p>

        <div className="flex gap-2">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            前
          </button>

          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`px-3 py-2 rounded-lg text-sm font-medium ${
                p === page
                  ? "bg-purple-600 text-white"
                  : "border border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {p}
            </button>
          ))}

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            次
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { VocabularyItem, CATEGORY_METADATA } from "@/types/vosk";
import { isoConvertDate } from "@/utils/iso-convert-date";
import { Pagination } from "./Pagination";

interface VoskVocabularyTableProps {
  items: VocabularyItem[];
  totalItems: number;
  page: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  onDeleteClick: (item: VocabularyItem) => void;
  onEditClick: (item: VocabularyItem) => void;
  hasFilter: boolean;
}

export function VoskVocabularyTable({
  items,
  totalItems,
  page,
  itemsPerPage,
  onPageChange,
  onDeleteClick,
  onEditClick,
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
                    onClick={() => onEditClick(item)}
                    className="px-3 py-1 border-2 border-blue-600 text-blue-600 hover:bg-blue-50 font-medium rounded"
                  >
                    編集
                  </button>
                  <button
                    onClick={() => onDeleteClick(item)}
                    className="px-3 py-1 border-2 border-red-600 text-red-600 hover:bg-red-50 font-medium rounded"
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
      <Pagination
        totalItems={totalItems}
        page={page}
        itemsPerPage={itemsPerPage}
        onPageChange={onPageChange}
      />
    </div>
  );
}

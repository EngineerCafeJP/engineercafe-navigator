"use client";

import { useMemo } from "react";

interface PaginationProps {
  totalItems: number;
  page: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
}

export function Pagination({
  totalItems,
  page,
  itemsPerPage,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const startItem = (page - 1) * itemsPerPage + 1;
  const endItem = Math.min(page * itemsPerPage, totalItems);

  // ページネーション表示範囲の計算（7ページ以上の場合は前後±2を表示）
  const paginationPages = useMemo(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }

    const pages: (number | string)[] = [];
    const range = 2; // 現在ページの前後2ページ

    // 最初のページ
    pages.push(1);

    // 開始と最初のページの間に省略が必要か
    if (page - range > 2) {
      pages.push("...");
    }

    // 現在ページの前後
    const start = Math.max(2, page - range);
    const end = Math.min(totalPages - 1, page + range);
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }

    // 終了と最後のページの間に省略が必要か
    if (page + range < totalPages - 1) {
      pages.push("...");
    }

    // 最後のページ
    if (totalPages > 1) {
      pages.push(totalPages);
    }

    return pages;
  }, [totalPages, page]);

  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-gray-600">
        全{totalItems}件中 {startItem}-{endItem}件を表示
      </p>

      <nav className="flex gap-2" aria-label="ページネーション">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          aria-label={`前のページ（現在: ${page}ページ目）`}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          前
        </button>

        {paginationPages.map((p, idx) =>
          p === "..." ? (
            <span
              key={`ellipsis-${idx}`}
              className="px-2 py-2 text-sm text-gray-600"
              aria-hidden="true"
            >
              ...
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              aria-current={p === page ? "page" : undefined}
              aria-label={`${p}ページ目`}
              className={`px-3 py-2 rounded-lg text-sm font-medium ${
                p === page
                  ? "bg-purple-600 text-white"
                  : "border border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {p}
            </button>
          )
        )}

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
          aria-label={`次のページ（現在: ${page}ページ目）`}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          次
        </button>
      </nav>
    </div>
  );
}

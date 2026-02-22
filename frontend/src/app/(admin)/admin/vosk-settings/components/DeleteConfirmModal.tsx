"use client";

import { VocabularyItem } from "@/types/vosk";

interface DeleteConfirmModalProps {
  item: VocabularyItem;
  isDeleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmModal({
  item,
  isDeleting,
  onConfirm,
  onCancel,
}: DeleteConfirmModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-lg shadow-lg p-6 max-w-sm w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          語彙を削除しますか？
        </h2>
        <p className="text-gray-700 mb-6">
          「{item.word}」を削除します。この操作は元に戻せません。
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-medium rounded-lg disabled:opacity-60 disabled:cursor-not-allowed"
          >
            キャンセル
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isDeleting ? "削除中..." : "削除する"}
          </button>
        </div>
      </div>
    </div>
  );
}

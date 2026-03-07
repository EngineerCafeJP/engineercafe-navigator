"use client";

import { VocabularyStats, CATEGORY_METADATA, CATEGORY_ORDER } from "@/types/vosk";

interface VoskVocabularyStatsProps {
  stats: VocabularyStats | null;
}

export function VoskVocabularyStats({ stats }: VoskVocabularyStatsProps) {
  return (
    <div className="space-y-6">
      {/* Quick Action */}
      <div>
        <button
          disabled
          title="この機能は準備中です"
          className="w-full px-4 py-2 bg-green-300 cursor-not-allowed opacity-60 text-white font-medium rounded-lg"
        >
          認識テスト
        </button>
      </div>

      {/* Statistics */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 mb-4">統計情報</h3>

        {stats ? (
          <div className="space-y-3">
            <div className="flex justify-between items-center border-b pb-3">
              <span className="text-gray-700">総登録数</span>
              <span className="font-semibold text-gray-900">{stats.total}件</span>
            </div>

            <div className="space-y-2">
              <p className="text-sm text-gray-600 font-medium">カテゴリ別内訳</p>
              {CATEGORY_ORDER.map((cat) => {
                const count = stats.byCategory[cat] || 0;
                // 0 件のカテゴリは表示しない
                if (count === 0) return null;

                return (
                  <div key={cat} className="flex justify-between text-sm">
                    <span className="text-gray-600">
                      {CATEGORY_METADATA[cat].label}
                    </span>
                    <span className="text-gray-900 font-medium">{count}件</span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">統計情報を読み込み中...</p>
        )}
      </div>
    </div>
  );
}

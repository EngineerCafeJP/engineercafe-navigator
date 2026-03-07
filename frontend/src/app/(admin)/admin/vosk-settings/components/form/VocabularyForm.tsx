"use client";

import React from "react";
import {
  VocabularyCategory,
  CATEGORY_METADATA,
  CATEGORY_ORDER,
} from "@/types/vosk";
import { VocabularyFormData, ValidationErrors } from "../../utils/validation";

interface VocabularyFormProps {
  data: VocabularyFormData;
  errors?: ValidationErrors;
  onWordChange: (value: string) => void;
  onReadingChange: (value: string) => void;
  onCategoryChange: (value: VocabularyCategory) => void;
  onPriorityChange: (value: number) => void;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
  isLoading: boolean;
  submitLabel?: string;
}

export const VocabularyForm = React.memo(function VocabularyForm({
  data,
  errors = {},
  onWordChange,
  onReadingChange,
  onCategoryChange,
  onPriorityChange,
  onSubmit,
  onCancel,
  isLoading,
  submitLabel = "登録",
}: VocabularyFormProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-6">
      {/* 単語 */}
      <div>
        <label
          htmlFor="word"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          単語 <span className="text-red-500">*</span>
        </label>
        <input
          id="word"
          type="text"
          value={data.word}
          onChange={(e) => onWordChange(e.target.value)}
          placeholder="エンジニアカフェ"
          className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
            isLoading ? "pointer-events-none" : ""
          } ${
            errors.word ? "border-red-500 bg-red-50" : "border-gray-300"
          }`}
        />
        {errors.word && (
          <p className="mt-1 text-sm text-red-600">{errors.word}</p>
        )}
      </div>

      {/* 読み仮名 */}
      <div>
        <label
          htmlFor="reading"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          読み仮名 <span className="text-red-500">*</span>
        </label>
        <input
          id="reading"
          type="text"
          value={data.reading}
          onChange={(e) => onReadingChange(e.target.value)}
          placeholder="えんじにあかふぇ"
          className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
            isLoading ? "pointer-events-none" : ""
          } ${
            errors.reading ? "border-red-500 bg-red-50" : "border-gray-300"
          }`}
        />
        {errors.reading && (
          <p className="mt-1 text-sm text-red-600">{errors.reading}</p>
        )}
      </div>

      {/* カテゴリ */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-3">
          カテゴリ <span className="text-red-500">*</span>
        </label>
        <div
          className={`space-y-2 p-3 rounded-lg ${errors.category ? "bg-red-50 border border-red-500" : ""}`}
        >
          {CATEGORY_ORDER.map((category) => (
            <label key={category} className="flex items-center">
              <input
                type="radio"
                name="category"
                value={category}
                checked={data.category === category}
                onChange={() => onCategoryChange(category)}
                className={`w-4 h-4 text-blue-600 focus:ring-2 focus:ring-blue-500 ${
                  isLoading ? "pointer-events-none" : ""
                }`}
              />
              <span className="ml-2 text-gray-700">
                {CATEGORY_METADATA[category].label}
              </span>
            </label>
          ))}
        </div>
        {errors.category && (
          <p className="mt-1 text-sm text-red-600">{errors.category}</p>
        )}
      </div>

      {/* 優先度 */}
      <div>
        <label
          htmlFor="priority"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          優先度（1-10）
        </label>
        <div className="flex items-center gap-4">
          <input
            id="priority"
            type="range"
            min="1"
            max="10"
            value={data.priority}
            onChange={(e) => onPriorityChange(parseInt(e.target.value, 10))}
            className={`flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer ${
              isLoading ? "pointer-events-none" : ""
            }`}
          />
          <span className="text-lg font-semibold text-gray-700 min-w-[2rem] text-center">
            {data.priority}
          </span>
        </div>
        <p className="mt-1 text-xs text-gray-500">
          優先度が高いほど音声認識で優先されます
        </p>
      </div>

      {/* ボタン */}
      <div className="flex gap-3 pt-6 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className={`flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 font-medium ${
            isLoading ? "pointer-events-none" : ""
          }`}
        >
          キャンセル
        </button>
        <button
          type="submit"
          className={`flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium ${
            isLoading ? "pointer-events-none" : ""
          }`}
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
});

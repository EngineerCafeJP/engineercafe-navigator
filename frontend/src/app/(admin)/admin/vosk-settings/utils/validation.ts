/**
 * Vosk Vocabulary Form Validation & Transformation using Zod
 */

import { z } from "zod";
import { VocabularyCategory, CATEGORY_ORDER } from "@/types/vosk";

export interface VocabularyFormData {
  word: string;
  reading: string;
  category: VocabularyCategory | "";
  priority: number;
}

// Zod バリデーションスキーマ
const vocabularySchema = z.object({
  word: z.string().min(1, "単語は必須です").trim(),
  reading: z.string().min(1, "読み仮名は必須です").trim(),
  category: z.enum(CATEGORY_ORDER, {
    errorMap: () => ({ message: "カテゴリは必須です" }),
  }),
});

/**
 * フィールド単位のエラー型
 */
export type ValidationErrors = Partial<Record<keyof VocabularyFormData, string>>;

/**
 * Zod を使用したバリデーション
 * フィールド単位のエラーを返す
 */
export function validateVocabularyForm(data: VocabularyFormData): ValidationErrors {
  const result = vocabularySchema.safeParse({
    word: data.word,
    reading: data.reading,
    category: data.category || undefined,
  });

  if (!result.success) {
    const errors: ValidationErrors = {};
    result.error.errors.forEach((error) => {
      const field = error.path[0] as keyof VocabularyFormData;
      errors[field] = error.message;
    });
    return errors;
  }

  return {};
}

/**
 * API送信用にデータを変換（作成・編集共通）
 */
export function transformVocabularyData(
  data: VocabularyFormData
): {
  word: string;
  reading: string;
  category: VocabularyCategory;
  priority: number;
} {
  return {
    word: data.word.trim(),
    reading: data.reading.trim(),
    category: data.category as VocabularyCategory,
    priority: data.priority,
  };
}

<<<<<<< HEAD
/**
 * Knowledge Upload Form Validation & Transformation using Zod
 */

=======
>>>>>>> origin/develop
import { z } from 'zod';

export interface KnowledgeUploadFormData {
  file: File | null;
  category: string;
  language: 'ja' | 'en';
  title: string;
}

<<<<<<< HEAD
// Zod バリデーションスキーマ
const uploadSchema = z.object({
  file: z.instanceof(File, { message: 'ファイルは必須です' })
    .refine(
      (file) => {
        const ext = file.name.split('.').pop()?.toLowerCase();
        return ext && ['pdf', 'md', 'markdown'].includes(ext);
      },
      'PDF または Markdown ファイルのみ対応しています'
    )
    .refine(
      (file) => file.size <= 10 * 1024 * 1024,
      'ファイルサイズは 10MB 以内にしてください'
    ),
  category: z.string().min(1, 'カテゴリは必須です'),
  language: z.enum(['ja', 'en'], {
    errorMap: () => ({ message: '言語は必須です' }),
  }),
  title: z.string().max(200, 'タイトルは 200 文字以内にしてください').optional(),
});

/**
 * フィールド単位のエラー型
 */
export type ValidationErrors = Partial<Record<keyof KnowledgeUploadFormData, string>>;

/**
 * Zod を使用したバリデーション
 * フィールド単位のエラーを返す
 */
export function validateKnowledgeUploadForm(
  data: KnowledgeUploadFormData
=======
const uploadSchema = z.object({
  file: z
    .instanceof(File, { message: 'ファイルは必須です' })
    .refine((file) => {
      const ext = file.name.split('.').pop()?.toLowerCase();
      return Boolean(ext && ['pdf', 'md', 'markdown'].includes(ext));
    }, 'PDF または Markdown ファイルのみ対応しています')
    .refine(
      (file) => file.size <= 10 * 1024 * 1024,
      'ファイルサイズは 10MB 以内にしてください',
    ),
  category: z.string().min(1, 'カテゴリは必須です'),
  language: z.enum(['ja', 'en']),
  title: z.string().max(200, 'タイトルは 200 文字以内にしてください').optional(),
});

export type ValidationErrors = Partial<Record<keyof KnowledgeUploadFormData, string>>;

export function validateKnowledgeUploadForm(
  data: KnowledgeUploadFormData,
>>>>>>> origin/develop
): ValidationErrors {
  const result = uploadSchema.safeParse({
    file: data.file,
    category: data.category,
    language: data.language,
    title: data.title || undefined,
  });

  if (!result.success) {
    const errors: ValidationErrors = {};
    result.error.errors.forEach((error) => {
      const field = error.path[0] as keyof KnowledgeUploadFormData;
      errors[field] = error.message;
    });
    return errors;
  }

  return {};
}

<<<<<<< HEAD
/**
 * API送信用にデータを変換
 */
export function transformKnowledgeUploadData(
  data: KnowledgeUploadFormData
=======
export function transformKnowledgeUploadData(
  data: KnowledgeUploadFormData,
>>>>>>> origin/develop
): {
  file: File;
  category: string;
  language: 'ja' | 'en';
  title?: string;
} {
  return {
    file: data.file as File,
    category: data.category.trim(),
    language: data.language,
    title: data.title ? data.title.trim() : undefined,
  };
}

import { z } from 'zod';

export interface KnowledgeUploadFormData {
  file: File | null;
  category: string;
  language: 'ja' | 'en';
  title: string;
}

// NOTE: We avoid `z.instanceof(File, ...)` at module top-level because the
// `File` global is only available in Node 20+ (and always in browsers). This
// module is evaluated at Next.js prerender time on Node, so referencing
// `File` directly there throws `ReferenceError: File is not defined` on
// Node 18. We perform the instance check lazily inside a superRefine,
// which only runs in the browser when validation is actually invoked.
// See issue #645.
//
// We use `superRefine` (instead of chained `.refine()` calls) so we can
// short-circuit after the type check fails — chained refines keep running
// even after a prior one returns false, which would crash on `file.name`
// when `value` is null/undefined (e.g. user submits without picking a file).
const fileSchema = z.unknown().superRefine((value, ctx) => {
  if (typeof File === 'undefined' || !(value instanceof File)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'ファイルは必須です',
    });
    return;
  }

  const ext = value.name.split('.').pop()?.toLowerCase();
  if (!ext || !['pdf', 'md', 'markdown'].includes(ext)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'PDF または Markdown ファイルのみ対応しています',
    });
  }

  if (value.size > 10 * 1024 * 1024) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'ファイルサイズは 10MB 以内にしてください',
    });
  }
});

const uploadSchema = z.object({
  file: fileSchema,
  category: z.string().min(1, 'カテゴリは必須です'),
  language: z.enum(['ja', 'en']),
  title: z.string().max(200, 'タイトルは 200 文字以内にしてください').optional(),
});

export type ValidationErrors = Partial<Record<keyof KnowledgeUploadFormData, string>>;

export function validateKnowledgeUploadForm(
  data: KnowledgeUploadFormData,
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

export function transformKnowledgeUploadData(
  data: KnowledgeUploadFormData,
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

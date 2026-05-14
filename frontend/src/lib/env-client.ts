/**
 * Client-side environment variable validation using Zod.
 *
 * Only NEXT_PUBLIC_* variables are available on the client side.
 * This module provides schema validation for those variables.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Schema: client-side (NEXT_PUBLIC_*) env vars
// ---------------------------------------------------------------------------

export const clientEnvSchema = z.object({
  // Supabase (required for client-side DB access)
  NEXT_PUBLIC_SUPABASE_URL: z
    .string()
    .trim()
    .url("NEXT_PUBLIC_SUPABASE_URL must be a valid URL (e.g. https://xxx.supabase.co)"),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z
    .string()
    .trim()
    .min(1, "NEXT_PUBLIC_SUPABASE_ANON_KEY is required"),

  // Backend URL visible to the browser. Used only by direct-call feature flags.
  NEXT_PUBLIC_BACKEND_API_URL: z.string().url().optional(),

  // Feature toggles (optional)
  NEXT_PUBLIC_ENABLE_FACIAL_EXPRESSION: z.string().optional(),
  NEXT_PUBLIC_USE_WEB_SPEECH_API: z.string().optional(),
  NEXT_PUBLIC_SKIP_BACKEND: z.string().optional(),
  NEXT_PUBLIC_QA_API_MODE: z.enum(['proxy', 'direct']).optional(),
});

export type ClientEnv = z.infer<typeof clientEnvSchema>;

// ---------------------------------------------------------------------------
// Validation function
// ---------------------------------------------------------------------------

export interface ClientEnvValidationResult {
  success: boolean;
  data?: ClientEnv;
  errors: string[];
}

/**
 * Validate client-side environment variables.
 *
 * Returns a result object; does not throw.
 */
export function validateClientEnv(): ClientEnvValidationResult {
  const envValues = {
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_BACKEND_API_URL: process.env.NEXT_PUBLIC_BACKEND_API_URL,
    NEXT_PUBLIC_ENABLE_FACIAL_EXPRESSION: process.env.NEXT_PUBLIC_ENABLE_FACIAL_EXPRESSION,
    NEXT_PUBLIC_USE_WEB_SPEECH_API: process.env.NEXT_PUBLIC_USE_WEB_SPEECH_API,
    NEXT_PUBLIC_SKIP_BACKEND: process.env.NEXT_PUBLIC_SKIP_BACKEND,
    NEXT_PUBLIC_QA_API_MODE: process.env.NEXT_PUBLIC_QA_API_MODE,
  };

  const result = clientEnvSchema.safeParse(envValues);

  if (result.success) {
    return { success: true, data: result.data, errors: [] };
  }

  const errors = result.error.issues.map(
    (issue) => `[MISSING] ${issue.path.join(".")}: ${issue.message}`
  );

  return { success: false, errors };
}

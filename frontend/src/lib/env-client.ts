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

  // COSCUP 2026 demo kiosk: starts in English when enabled (default: off)
  NEXT_PUBLIC_DEMO_MODE: z.string().optional(),
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
    NEXT_PUBLIC_DEMO_MODE: process.env.NEXT_PUBLIC_DEMO_MODE,
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

// ---------------------------------------------------------------------------
// Demo-mode helpers
// ---------------------------------------------------------------------------

/**
 * True when NEXT_PUBLIC_DEMO_MODE === 'true' (COSCUP 2026 demo kiosk).
 *
 * Follows the same direct process.env parse convention as other NEXT_PUBLIC
 * feature flags (e.g. NEXT_PUBLIC_PARALLEL_VOICE_FILLER in
 * app/components/voice-interface/constants.ts).
 */
export function isDemoMode(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
}

/**
 * Default kiosk UI language: 'en' during demo mode, otherwise 'ja'.
 * Used as the lazy initializer for the kiosk language state and as the
 * first-run settings modal preselection.
 */
export function getDefaultKioskLanguage(): 'ja' | 'en' {
  return isDemoMode() ? 'en' : 'ja';
}

/**
 * TTS provider for assistant speech: 'kokoro' during demo mode (no local
 * piper-plus server in the demo stack), otherwise 'piper'.
 */
export function getTtsProvider(): string {
  return isDemoMode() ? 'kokoro' : 'piper';
}

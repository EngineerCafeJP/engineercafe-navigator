/**
 * Server-side environment variable validation using Zod for the vars tracked in
 * frontend/.env.example.
 *
 * It does NOT replace direct process.env usage in individual files yet, and it
 * does not attempt to validate platform-managed/runtime flags such as NODE_ENV.
 *
 * Usage:
 *   import { validateServerEnv } from '@/lib/env';
 *   const result = validateServerEnv();
 *   if (!result.success) { /* handle missing vars *\/ }
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Schema: required server-side env vars (core functionality)
// ---------------------------------------------------------------------------

const requiredServerEnvSchema = z.object({
  // Supabase
  NEXT_PUBLIC_SUPABASE_URL: z
    .string()
    .url("NEXT_PUBLIC_SUPABASE_URL must be a valid URL (e.g. https://xxx.supabase.co)"),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z
    .string()
    .min(1, "NEXT_PUBLIC_SUPABASE_ANON_KEY is required"),

  // Backend proxy
  BACKEND_API_URL: z
    .string()
    .url("BACKEND_API_URL must be a valid URL"),
  BACKEND_API_KEY: z
    .string()
    .min(1, "BACKEND_API_KEY is required"),
});

// ---------------------------------------------------------------------------
// Schema: optional server-side env vars (graceful degradation)
// ---------------------------------------------------------------------------

const optionalServerEnvSchema = z.object({
  // Server-only admin, alerting, and cron features
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),
  ADMIN_API_SECRET: z.string().optional(),
  CRON_SECRET: z.string().optional(),
  OPENROUTER_API_KEY: z.string().optional(),

  // Alerting
  ALERT_WEBHOOK_SECRET: z.string().optional(),
  SLACK_WEBHOOK_URL: z.string().optional(),

  // Redis cache
  UPSTASH_REDIS_URL: z.string().optional(),
  UPSTASH_REDIS_TOKEN: z.string().optional(),

  // Feature flags
  NEXT_PUBLIC_ENABLE_FACIAL_EXPRESSION: z.string().optional(),
  NEXT_PUBLIC_USE_WEB_SPEECH_API: z.string().optional(),
  NEXT_PUBLIC_SKIP_BACKEND: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Combined schema
// ---------------------------------------------------------------------------

export const serverEnvSchema = requiredServerEnvSchema.merge(optionalServerEnvSchema);

export type ServerEnv = z.infer<typeof serverEnvSchema>;

// ---------------------------------------------------------------------------
// Validation function
// ---------------------------------------------------------------------------

export interface EnvValidationResult {
  success: boolean;
  data?: ServerEnv;
  errors: string[];
  warnings: string[];
}

/**
 * Validate all server-side environment variables.
 *
 * Returns a result object instead of throwing so callers can decide
 * how to handle missing vars (warn in dev, fail in prod, etc.).
 */
export function validateServerEnv(): EnvValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // Validate required vars
  const requiredResult = requiredServerEnvSchema.safeParse(process.env);
  if (!requiredResult.success) {
    for (const issue of requiredResult.error.issues) {
      errors.push(`[MISSING] ${issue.path.join(".")}: ${issue.message}`);
    }
  }

  // Validate optional vars (collect warnings for missing recommended ones)
  const recommendedOptional = [
    "SUPABASE_SERVICE_ROLE_KEY",
    "ADMIN_API_SECRET",
    "CRON_SECRET",
  ] as const;

  for (const key of recommendedOptional) {
    if (!process.env[key]) {
      warnings.push(
        `[RECOMMENDED] ${key} is not set — some features may be unavailable`
      );
    }
  }

  if (!process.env.OPENROUTER_API_KEY) {
    warnings.push(
      "[REQUIRED_CRON] OPENROUTER_API_KEY is not set — /api/cron/update-knowledge-base Connpass sync will fail"
    );
  }

  // Full parse for the combined schema (optional fields default to undefined)
  const fullResult = serverEnvSchema.safeParse(process.env);

  return {
    success: errors.length === 0,
    data: fullResult.success ? fullResult.data : undefined,
    errors,
    warnings,
  };
}

// ---------------------------------------------------------------------------
// Dev-only startup validation
// ---------------------------------------------------------------------------

/**
 * Run validation and log results. Intended for dev startup only.
 * Does NOT throw — just warns via console.warn.
 */
export function logEnvValidation(): void {
  if (process.env.NODE_ENV === "production") {
    return;
  }

  const result = validateServerEnv();

  if (result.errors.length > 0) {
    console.warn(
      "\n⚠ Environment variable validation errors:\n" +
        result.errors.map((e) => `  ${e}`).join("\n") +
        "\n"
    );
  }

  if (result.warnings.length > 0) {
    console.warn(
      "\nℹ Environment variable warnings:\n" +
        result.warnings.map((w) => `  ${w}`).join("\n") +
        "\n"
    );
  }

  if (result.success && result.warnings.length === 0) {
    console.warn("✓ All environment variables validated successfully.\n");
  }
}

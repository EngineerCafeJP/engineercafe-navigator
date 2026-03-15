/**
 * Server-side environment variable validation using Zod.
 *
 * This module defines schemas for ALL server-side env vars used across
 * the frontend codebase. It does NOT replace direct process.env usage
 * in individual files yet — that is a separate refactor step.
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

  // Google Cloud
  GOOGLE_CLOUD_PROJECT_ID: z
    .string()
    .min(1, "GOOGLE_CLOUD_PROJECT_ID is required"),
  GOOGLE_CLOUD_CREDENTIALS: z
    .string()
    .min(1, "GOOGLE_CLOUD_CREDENTIALS path is required"),

  // Next.js auth
  NEXTAUTH_URL: z.string().url("NEXTAUTH_URL must be a valid URL"),
  NEXTAUTH_SECRET: z.string().min(1, "NEXTAUTH_SECRET is required"),
});

// ---------------------------------------------------------------------------
// Schema: optional server-side env vars (graceful degradation)
// ---------------------------------------------------------------------------

const optionalServerEnvSchema = z.object({
  // Admin features
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),

  // Gemini model override
  GEMINI_MODEL: z.string().optional(),
  GEMINI_API_KEY: z.string().optional(),

  // AI / DB integrations used by optional workflows
  GOOGLE_GENERATIVE_AI_API_KEY: z.string().optional(),
  OPENAI_API_KEY: z.string().optional(),
  POSTGRES_URL: z.string().optional(),

  // Google Cloud services
  GOOGLE_SPEECH_API_KEY: z.string().optional(),
  GOOGLE_TRANSLATE_API_KEY: z.string().optional(),
  GOOGLE_APPLICATION_CREDENTIALS: z.string().optional(),

  // Google Calendar OAuth2
  GOOGLE_CALENDAR_ICAL_URL: z.string().optional(),
  GOOGLE_CALENDAR_CLIENT_ID: z.string().optional(),
  GOOGLE_CALENDAR_CLIENT_SECRET: z.string().optional(),
  GOOGLE_CALENDAR_REDIRECT_URI: z.string().optional(),
  ENGINEER_CAFE_CALENDAR_ID: z.string().optional(),

  // Alert / monitoring
  ALERT_WEBHOOK_SECRET: z.string().optional(),
  SLACK_WEBHOOK_URL: z.string().optional(),

  // CRON authentication
  CRON_SECRET: z.string().optional(),

  // Redis cache
  UPSTASH_REDIS_URL: z.string().optional(),
  UPSTASH_REDIS_TOKEN: z.string().optional(),

  // External integrations
  WEBSOCKET_URL: z.string().optional(),
  RECEPTION_API_URL: z.string().optional(),

  // Vercel
  VERCEL_URL: z.string().optional(),
  VERCEL_DEPLOYMENT_ID: z.string().optional(),

  // Feature flags
  FF_NEW_EMBEDDINGS_PERCENTAGE: z.string().optional(),
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
    "CRON_SECRET",
    "GOOGLE_GENERATIVE_AI_API_KEY",
  ] as const;

  for (const key of recommendedOptional) {
    if (!process.env[key]) {
      warnings.push(
        `[RECOMMENDED] ${key} is not set — some features may be unavailable`
      );
    }
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

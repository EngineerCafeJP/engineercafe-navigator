/**
 * Next.js Instrumentation — runs once on server startup.
 * https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 *
 * Validates required server environment variables and fails fast
 * if critical configuration is missing in production.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { validateServerEnv } = await import("@/lib/env");
    const result = validateServerEnv();

    if (!result.success) {
      for (const err of result.errors) {
        console.error(`[instrumentation] ${err}`);
      }

      if (process.env.NODE_ENV === "production") {
        throw new Error(
          `Server startup blocked: ${result.errors.length} missing env var(s). ` +
            `See logs above for details.`
        );
      }

      console.warn(
        "[instrumentation] Non-production mode: continuing despite missing env vars."
      );
    }
  }
}

/**
 * Maintenance mode for the public Vercel deployment.
 *
 * The GCP backend and the Supabase project behind Vercel production were
 * retired on 2026-09-27 while the navigator moves to local operation
 * (docs/plans/local-operation-migration-2026-09-27.md). Vercel production
 * therefore serves a maintenance response by default. Local runs are not
 * affected because Vercel sets VERCEL_ENV only on its own deployments.
 *
 * MAINTENANCE_MODE overrides the default in either direction:
 * - on / true / 1: always serve the maintenance response
 * - off / false / 0: never serve it (set this once a backend is back)
 *
 * While maintenance mode is on, the build-time env check and the startup
 * validation skip the backend and Supabase credentials, so the maintenance
 * page still deploys after those credentials are removed.
 *
 * This module has no Next.js imports so build scripts can use it.
 */
export interface MaintenanceModeEnv {
  readonly MAINTENANCE_MODE?: string;
  readonly VERCEL_ENV?: string;
}

const ENABLED_VALUES: ReadonlySet<string> = new Set(['on', 'true', '1']);
const DISABLED_VALUES: ReadonlySet<string> = new Set(['off', 'false', '0']);

export function isMaintenanceMode(env: MaintenanceModeEnv): boolean {
  const override = env.MAINTENANCE_MODE?.trim().toLowerCase() ?? '';

  if (ENABLED_VALUES.has(override)) {
    return true;
  }

  if (DISABLED_VALUES.has(override)) {
    return false;
  }

  return env.VERCEL_ENV === 'production';
}

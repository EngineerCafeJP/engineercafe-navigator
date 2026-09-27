import { NextResponse } from 'next/server';

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
 */
export interface MaintenanceModeEnv {
  readonly MAINTENANCE_MODE?: string;
  readonly VERCEL_ENV?: string;
}

const ENABLED_VALUES: ReadonlySet<string> = new Set(['on', 'true', '1']);
const DISABLED_VALUES: ReadonlySet<string> = new Set(['off', 'false', '0']);

// One day; tells crawlers and clients that the outage is temporary.
const RETRY_AFTER_SECONDS = '86400';

const MAINTENANCE_HTML = `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>メンテナンス中 | Engineer Cafe Navigator</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f7f7f5; color: #1f2933; font-family: system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; }
  main { max-width: 32rem; padding: 2rem 1.5rem; text-align: center; line-height: 1.8; }
  h1 { margin: 0 0 1rem; font-size: 1.5rem; }
  p { margin: 0.5rem 0; }
  .en { color: #52606d; font-size: 0.95rem; }
  @media (prefers-color-scheme: dark) {
    body { background: #111418; color: #e4e7eb; }
    .en { color: #9aa5b1; }
  }
</style>
</head>
<body>
<main>
<h1>メンテナンス中です</h1>
<p>Engineer Cafe Navigator は、現在公開を停止しています。</p>
<p>再開まで、しばらくお待ちください。</p>
<p class="en" lang="en">Engineer Cafe Navigator is currently unavailable for maintenance.</p>
</main>
</body>
</html>
`;

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

function isApiRoute(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

export function maintenanceResponse(pathname: string): NextResponse {
  const headers = {
    'cache-control': 'no-store',
    'retry-after': RETRY_AFTER_SECONDS,
  };

  if (isApiRoute(pathname)) {
    return NextResponse.json(
      { error: 'Service Unavailable', reason: 'maintenance' },
      { status: 503, headers },
    );
  }

  return new NextResponse(MAINTENANCE_HTML, {
    status: 503,
    headers: { ...headers, 'content-type': 'text/html; charset=utf-8' },
  });
}

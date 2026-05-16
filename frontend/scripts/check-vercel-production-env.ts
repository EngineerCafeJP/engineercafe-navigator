#!/usr/bin/env tsx

import {
  getMissingProductionRequiredVercelEnvKeys,
  productionRequiredVercelEnvKeys,
  validateServerEnv,
} from "../src/lib/env";

const args = new Set(process.argv.slice(2));
const shouldForce = args.has("--force") || args.has("--production");
const requiredVercelEnvironments = new Set(["production", "preview"]);
const shouldCheck =
  shouldForce || requiredVercelEnvironments.has(process.env.VERCEL_ENV ?? "");

if (args.has("--help") || args.has("-h")) {
  console.log(`Usage: pnpm env:check:production [--force]

Checks Vercel production/preview-required frontend env vars without printing values.
By default this runs only when VERCEL_ENV=production or VERCEL_ENV=preview. Use --force in CI or local smoke checks.`);
  process.exit(0);
}

if (!shouldCheck) {
  console.log(
    `[env-check] skipped: VERCEL_ENV=${process.env.VERCEL_ENV ?? "(unset)"} is not production or preview.`
  );
  process.exit(0);
}

const missingKeys = getMissingProductionRequiredVercelEnvKeys();
const result = validateServerEnv();

if (!result.success) {
  console.error("[env-check] Vercel production env check failed.");

  if (missingKeys.length > 0) {
    console.error(
      `[env-check] Missing required env var(s): ${missingKeys.join(", ")}`
    );
  }

  for (const error of result.errors) {
    console.error(`[env-check] ${error}`);
  }

  console.error("[env-check] Secret values are intentionally not printed.");
  process.exit(1);
}

console.log(
  `[env-check] Vercel production env check passed (${productionRequiredVercelEnvKeys.length} required vars checked).`
);

#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const repoRoot = resolve(import.meta.dirname, '..');
const vercelConfigPath = resolve(repoRoot, 'frontend/vercel.json');
const proxyConfigPath = resolve(repoRoot, 'frontend/src/lib/api/backend-proxy.ts');
const workflowPath = resolve(repoRoot, '.github/workflows/ci.yml');

function usage() {
  console.log(`Usage: node scripts/validate-p0-cloudrun-vercel-timeouts.mjs [options]

Options:
  --live                         Describe live Cloud Run services with gcloud.
  --skip-live                    Skip live Cloud Run checks.
  --project ID                   GCP project for live checks.
  --service NAME                 Backend Cloud Run service.
  --region REGION                Backend Cloud Run region.
  --piper-plus-service NAME      Piper Plus Cloud Run service.
  --piper-plus-region REGION     Piper Plus Cloud Run region.
  -h, --help                     Show this help.

Environment:
  CHECK_LIVE_CLOUD_RUN=1         Enables live checks when --live is not passed.
  CLOUD_RUN_PROJECT              Default project for live checks.
`);
}

const args = process.argv.slice(2);
const cli = {
  live: process.env.CHECK_LIVE_CLOUD_RUN === '1',
  project: process.env.CLOUD_RUN_PROJECT || process.env.GCP_PROJECT || process.env.GOOGLE_CLOUD_PROJECT || '',
};

for (let index = 0; index < args.length; index += 1) {
  const arg = args[index];
  const next = () => {
    index += 1;
    if (index >= args.length || args[index].startsWith('-')) {
      console.error(`Missing value for ${arg}`);
      process.exit(2);
    }
    return args[index];
  };

  if (arg === '--live') cli.live = true;
  else if (arg === '--skip-live') cli.live = false;
  else if (arg === '--project') cli.project = next();
  else if (arg === '--service') process.env.CLOUD_RUN_SERVICE = next();
  else if (arg === '--region') process.env.CLOUD_RUN_REGION = next();
  else if (arg === '--piper-plus-service') process.env.PIPER_PLUS_SERVICE = next();
  else if (arg === '--piper-plus-region') process.env.PIPER_PLUS_REGION = next();
  else if (arg === '-h' || arg === '--help') {
    usage();
    process.exit(0);
  } else {
    console.error(`Unknown option: ${arg}`);
    usage();
    process.exit(2);
  }
}

const expected = {
  service: process.env.CLOUD_RUN_SERVICE || 'engineer-cafe-backend',
  region: process.env.CLOUD_RUN_REGION || 'asia-northeast1',
  minScale: 5,
  maxScale: 15,
  containerConcurrency: 1,
  timeoutSeconds: 300,
  startupCpuBoost: true,
  cpuThrottling: false,
  vercelMaxDurationSeconds: 120,
  proxyTimeoutMs: 110_000,
};

const expectedPiperPlus = {
  service: process.env.PIPER_PLUS_SERVICE || 'piper-plus',
  region: process.env.PIPER_PLUS_REGION || 'asia-northeast1',
  minScale: 2,
  maxScale: 10,
  containerConcurrency: 4,
  timeoutSeconds: 300,
  startupCpuBoost: true,
  cpuThrottling: false,
};

function fail(message) {
  console.error(`P0 timeout validation failed: ${message}`);
  process.exitCode = 1;
}

const vercel = JSON.parse(readFileSync(vercelConfigPath, 'utf8'));
for (const routePath of [
  'src/app/api/voice/route.ts',
  'src/app/api/voice/filler/route.ts',
  'src/app/api/qa/route.ts',
]) {
  const maxDuration = vercel.functions?.[routePath]?.maxDuration;
  if (maxDuration !== expected.vercelMaxDurationSeconds) {
    fail(`${routePath} maxDuration must be ${expected.vercelMaxDurationSeconds}s, got ${maxDuration}`);
  }
}

const proxySource = readFileSync(proxyConfigPath, 'utf8');
if (!proxySource.includes('BACKEND_PROXY_TIMEOUT_MS = 110_000')) {
  fail(`backend proxy timeout must be ${expected.proxyTimeoutMs}ms`);
}

const workflowSource = readFileSync(workflowPath, 'utf8');
for (const requiredDeployFlag of [
  '--min-instances 5',
  '--max-instances 15',
  '--cpu-boost',
  '--no-cpu-throttling',
]) {
  if (!workflowSource.includes(requiredDeployFlag)) {
    fail(`backend deploy workflow must include ${requiredDeployFlag}`);
  }
}

if (expected.proxyTimeoutMs >= expected.vercelMaxDurationSeconds * 1000) {
  fail('proxy timeout must stay below Vercel maxDuration');
}

if (expected.vercelMaxDurationSeconds >= expected.timeoutSeconds) {
  fail('Vercel maxDuration must stay below Cloud Run timeoutSeconds=300');
}

function describeCloudRunService(serviceName, region) {
  const commandArgs = [
    'run',
    'services',
    'describe',
    serviceName,
    '--region',
    region,
    '--format=json',
  ];
  if (cli.project) {
    commandArgs.push('--project', cli.project);
  }

  const output = execFileSync(
    'gcloud',
    commandArgs,
    { encoding: 'utf8' },
  );
  return JSON.parse(output);
}

function validateLiveService(service, config) {
  const annotations = service.spec?.template?.metadata?.annotations ?? {};
  const spec = service.spec?.template?.spec ?? {};

  const minScale = Number(annotations['autoscaling.knative.dev/minScale']);
  const maxScale = Number(annotations['autoscaling.knative.dev/maxScale']);
  const containerConcurrency = Number(spec.containerConcurrency);
  const timeoutSeconds = Number(spec.timeoutSeconds);
  const startupCpuBoost = annotations['run.googleapis.com/startup-cpu-boost'] === 'true';
  const cpuThrottling = annotations['run.googleapis.com/cpu-throttling'] !== 'false';

  if (minScale < config.minScale) fail(`${config.service} minScale must be >= ${config.minScale}, got ${minScale}`);
  if (maxScale < config.maxScale) fail(`${config.service} maxScale must be >= ${config.maxScale}, got ${maxScale}`);
  if (containerConcurrency !== config.containerConcurrency) {
    fail(`${config.service} containerConcurrency must be ${config.containerConcurrency}, got ${containerConcurrency}`);
  }
  if (timeoutSeconds !== config.timeoutSeconds) {
    fail(`${config.service} timeoutSeconds must be ${config.timeoutSeconds}, got ${timeoutSeconds}`);
  }
  if (startupCpuBoost !== config.startupCpuBoost) fail(`${config.service} startup CPU boost must be enabled`);
  if (cpuThrottling !== config.cpuThrottling) fail(`${config.service} CPU throttling must be disabled`);
}

if (cli.live) {
  try {
    validateLiveService(describeCloudRunService(expected.service, expected.region), expected);
    validateLiveService(describeCloudRunService(expectedPiperPlus.service, expectedPiperPlus.region), expectedPiperPlus);
  } catch (error) {
    fail(`could not describe live Cloud Run services: ${error instanceof Error ? error.message : String(error)}`);
  }
} else {
  console.log('Skipping live Cloud Run describe; pass --live or set CHECK_LIVE_CLOUD_RUN=1 to verify deployed service settings.');
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log('P0 Vercel/Cloud Run timeout settings validated.');

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { dispatchCronAlert } from '../../lib/monitoring/cron-alerts';
import type { CronAlertContext } from '../../lib/monitoring/cron-alerts';

const env = process.env as Record<string, string | undefined>;
const originalWebhookUrl = env.CRON_SLACK_WEBHOOK_URL;
const originalDeploymentUrl = env.VERCEL_DEPLOYMENT_URL;
const originalFetch = global.fetch;
const originalConsoleError = console.error;

const baseContext: CronAlertContext = {
  cronName: '/api/cron/update-knowledge-base',
  startTime: Date.UTC(2026, 4, 3, 2, 0, 0),
  duration: 1234,
  error: new Error('Supabase request timed out'),
  metricsTracked: true,
};

afterEach(() => {
  if (originalWebhookUrl === undefined) {
    delete env.CRON_SLACK_WEBHOOK_URL;
  } else {
    env.CRON_SLACK_WEBHOOK_URL = originalWebhookUrl;
  }

  if (originalDeploymentUrl === undefined) {
    delete env.VERCEL_DEPLOYMENT_URL;
  } else {
    env.VERCEL_DEPLOYMENT_URL = originalDeploymentUrl;
  }

  global.fetch = originalFetch;
  console.error = originalConsoleError;
});

test(
  'logs and does not throw when the Slack webhook URL is unset',
  { concurrency: false },
  async () => {
    delete env.CRON_SLACK_WEBHOOK_URL;
    const errors: unknown[][] = [];
    console.error = (...args: unknown[]) => {
      errors.push(args);
    };

    await assert.doesNotReject(dispatchCronAlert(baseContext));

    assert.equal(errors.length, 1);
    assert.match(String(errors[0][0]), /CRON_SLACK_WEBHOOK_URL is not set/);
  }
);

test(
  'posts a Slack incoming webhook payload when configured',
  { concurrency: false },
  async () => {
    env.CRON_SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/test';
    env.VERCEL_DEPLOYMENT_URL = 'engineer-cafe.vercel.app';
    let capturedUrl: string | URL | Request | undefined;
    let capturedInit: RequestInit | undefined;

    global.fetch = (async (input, init) => {
      capturedUrl = input;
      capturedInit = init;
      return new Response('ok', { status: 200 });
    }) as typeof fetch;

    await dispatchCronAlert(baseContext);

    assert.equal(capturedUrl, 'https://hooks.slack.example/services/test');
    assert.equal(capturedInit?.method, 'POST');
    assert.deepEqual(capturedInit?.headers, { 'Content-Type': 'application/json' });

    const body = JSON.parse(String(capturedInit?.body)) as Record<string, unknown>;
    assert.equal(
      body.text,
      'Cron failure: /api/cron/update-knowledge-base (Supabase request timed out)'
    );
    assert.match(JSON.stringify(body), /engineer-cafe\.vercel\.app/);
  }
);

test(
  'logs and does not throw when fetch rejects',
  { concurrency: false },
  async () => {
    env.CRON_SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/test';
    const errors: unknown[][] = [];
    console.error = (...args: unknown[]) => {
      errors.push(args);
    };
    global.fetch = (async () => {
      throw new Error('network down');
    }) as typeof fetch;

    await assert.doesNotReject(dispatchCronAlert(baseContext));

    assert.equal(errors.length, 1);
    assert.match(String(errors[0][0]), /Failed to dispatch Slack cron alert/);
  }
);

test(
  'includes cron name, duration, and error message in the payload',
  { concurrency: false },
  async () => {
    env.CRON_SLACK_WEBHOOK_URL = 'https://hooks.slack.example/services/test';
    let payload = '';

    global.fetch = (async (_input, init) => {
      payload = String(init?.body);
      return new Response('ok', { status: 200 });
    }) as typeof fetch;

    await dispatchCronAlert(baseContext);

    assert.match(payload, /\/api\/cron\/update-knowledge-base/);
    assert.match(payload, /1234ms/);
    assert.match(payload, /Supabase request timed out/);
  }
);

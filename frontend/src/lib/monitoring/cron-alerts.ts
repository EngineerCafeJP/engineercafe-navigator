export interface CronAlertContext {
  cronName: string;
  startTime: number;
  duration: number;
  error?: Error;
  metricsTracked: boolean;
}

interface SlackBlock {
  type: 'section' | 'context';
  text?: {
    type: 'mrkdwn';
    text: string;
  };
  fields?: Array<{
    type: 'mrkdwn';
    text: string;
  }>;
  elements?: Array<{
    type: 'mrkdwn';
    text: string;
  }>;
}

interface SlackPayload {
  text: string;
  blocks: SlackBlock[];
}

const ALERT_PREFIX = '[CRON_ALERT]';

function formatIsoTime(timestamp: number): string {
  return new Date(timestamp).toISOString();
}

function getDeploymentUrl(): string | undefined {
  const deploymentUrl = process.env.VERCEL_DEPLOYMENT_URL;

  if (!deploymentUrl) {
    return undefined;
  }

  return deploymentUrl.startsWith('http') ? deploymentUrl : `https://${deploymentUrl}`;
}

function buildSlackPayload(ctx: CronAlertContext): SlackPayload {
  const startedAt = formatIsoTime(ctx.startTime);
  const deploymentUrl = getDeploymentUrl();
  const errorMessage = ctx.error?.message ?? 'Unknown error';
  const fields = [
    `*Cron*\n${ctx.cronName}`,
    `*Duration*\n${ctx.duration}ms`,
    `*Started at*\n${startedAt}`,
    `*Metrics tracked*\n${ctx.metricsTracked ? 'yes' : 'no'}`,
  ];

  if (deploymentUrl) {
    fields.push(`*Deployment*\n${deploymentUrl}`);
  }

  return {
    text: `Cron failure: ${ctx.cronName} (${errorMessage})`,
    blocks: [
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `:rotating_light: *Cron failure detected*\n${ctx.cronName}`,
        },
      },
      {
        type: 'section',
        fields: fields.map((text) => ({ type: 'mrkdwn', text })),
      },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `*Error*\n${errorMessage}`,
        },
      },
      {
        type: 'context',
        elements: [
          {
            type: 'mrkdwn',
            text: 'Check Vercel runtime logs, then follow docs/runbook/cron-failure.md.',
          },
        ],
      },
    ],
  };
}

export async function dispatchCronAlert(ctx: CronAlertContext): Promise<void> {
  const webhookUrl = process.env.CRON_SLACK_WEBHOOK_URL;
  const payload = buildSlackPayload(ctx);

  if (!webhookUrl) {
    console.error(`${ALERT_PREFIX} CRON_SLACK_WEBHOOK_URL is not set`, payload);
    return;
  }

  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error(
        `${ALERT_PREFIX} Slack webhook returned ${response.status} ${response.statusText}`,
        payload
      );
    }
  } catch (error) {
    console.error(`${ALERT_PREFIX} Failed to dispatch Slack cron alert`, error, payload);
  }
}

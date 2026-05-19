export type VoiceTelemetryEvent = string;

export type VoiceTelemetryTransport = 'sendBeacon' | 'fetch' | 'skipped';

export interface VoiceTelemetryPayload {
  readonly event: VoiceTelemetryEvent;
  readonly timestamp?: string;
  readonly userAgent?: string;
  readonly [key: string]: unknown;
}

export interface VoiceTelemetryOptions {
  readonly endpoint?: string;
}

const DEFAULT_VOICE_TELEMETRY_ENDPOINT = '/api/telemetry/voice';

function createPayload(
  event: VoiceTelemetryEvent,
  details: Record<string, unknown> = {},
): VoiceTelemetryPayload {
  return {
    ...details,
    event,
    timestamp: new Date().toISOString(),
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
  };
}

function toJsonBlob(payload: VoiceTelemetryPayload): Blob {
  return new Blob([JSON.stringify(payload)], { type: 'application/json' });
}

async function postWithKeepalive(endpoint: string, payload: VoiceTelemetryPayload): Promise<void> {
  if (typeof fetch !== 'function') {
    return;
  }

  await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    keepalive: true,
  });
}

export async function sendVoiceTelemetry(
  event: VoiceTelemetryEvent,
  details: Record<string, unknown> = {},
  options: VoiceTelemetryOptions = {},
): Promise<VoiceTelemetryTransport> {
  const endpoint = options.endpoint ?? DEFAULT_VOICE_TELEMETRY_ENDPOINT;
  const payload = createPayload(event, details);

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    try {
      if (navigator.sendBeacon(endpoint, toJsonBlob(payload))) {
        return 'sendBeacon';
      }
    } catch {
      // Fall through to fetch keepalive below.
    }
  }

  if (typeof fetch === 'function') {
    await postWithKeepalive(endpoint, payload);
    return 'fetch';
  }

  return 'skipped';
}

export function emitVoiceTelemetry(
  event: VoiceTelemetryEvent,
  details: Record<string, unknown> = {},
  options: VoiceTelemetryOptions = {},
): void {
  void sendVoiceTelemetry(event, details, options).catch(() => {
    /* best-effort telemetry must not affect voice UX */
  });
}

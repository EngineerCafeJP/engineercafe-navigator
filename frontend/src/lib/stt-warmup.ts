const STT_WARMUP_REQUEST_TIMEOUT_MS = 5000;

let warmupAbortController: AbortController | null = null;
let warmupTimeoutId: ReturnType<typeof setTimeout> | null = null;

export function sendSttWarmup({
  language = 'ja',
  sessionId,
}: {
  language?: string;
  sessionId?: string;
} = {}): void {
  if (warmupAbortController) {
    return;
  }
  const controller = new AbortController();
  warmupAbortController = controller;
  warmupTimeoutId = setTimeout(() => {
    controller.abort();
  }, STT_WARMUP_REQUEST_TIMEOUT_MS);

  const body: Record<string, string> = { action: 'warmup', language };
  if (sessionId) {
    body.sessionId = sessionId;
  }

  fetch('/api/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .catch(() => {})
    .finally(() => {
      if (warmupAbortController !== controller) {
        return;
      }
      if (warmupTimeoutId) {
        clearTimeout(warmupTimeoutId);
        warmupTimeoutId = null;
      }
      warmupAbortController = null;
    });
}

export function cancelSttWarmup(): void {
  warmupAbortController?.abort();
  if (warmupTimeoutId) {
    clearTimeout(warmupTimeoutId);
    warmupTimeoutId = null;
  }
  warmupAbortController = null;
}

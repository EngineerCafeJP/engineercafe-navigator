export const RECEPTION_NARRATION_MIN_SLIDE_DWELL_MS = 4_000;

type AdvanceDelayInput = {
  slideShownAtMs: number;
  nowMs: number;
  requestedDelayMs: number;
  minimumDwellMs?: number;
};

function safeNonNegativeMs(value: number, fallback = 0): number {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function getReceptionNarrationAdvanceDelay({
  slideShownAtMs,
  nowMs,
  requestedDelayMs,
  minimumDwellMs = RECEPTION_NARRATION_MIN_SLIDE_DWELL_MS,
}: AdvanceDelayInput): number {
  const requested = safeNonNegativeMs(requestedDelayMs);
  const minimum = safeNonNegativeMs(minimumDwellMs);
  const elapsed = safeNonNegativeMs(nowMs - slideShownAtMs);

  return Math.max(requested, minimum - elapsed, 0);
}

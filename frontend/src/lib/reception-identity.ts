import type { OcrResponse } from '@/lib/api/ocr-api';
import type { VisitorIdentity } from '@/lib/reception-api';

function readFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readNonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function readLastPurpose(value: unknown): VisitorIdentity['last_purpose'] | undefined {
  if (!value || typeof value !== 'object') {
    return undefined;
  }

  const category = readNonEmptyString((value as { category?: unknown }).category);
  if (!category) {
    return undefined;
  }

  return {
    category,
    detail: readNonEmptyString((value as { detail?: unknown }).detail),
  };
}

export function createVisitorIdentityFromOcr(
  result: OcrResponse,
): VisitorIdentity | undefined {
  const rawIdentity = result.visitor_identity;
  if (!rawIdentity || typeof rawIdentity !== 'object') {
    return undefined;
  }

  const userId = readFiniteNumber(rawIdentity.user_id);
  if (userId === undefined) {
    return undefined;
  }

  const identity: VisitorIdentity = {
    user_id: userId,
  };
  const name = readNonEmptyString(rawIdentity.name) ?? readNonEmptyString(result.recognized_text);
  const visitCount = readFiniteNumber(rawIdentity.visit_count);
  const lastPurpose = readLastPurpose(rawIdentity.last_purpose);

  if (name) {
    identity.name = name;
  }
  if (visitCount !== undefined) {
    identity.visit_count = visitCount;
  }
  if (lastPurpose) {
    identity.last_purpose = lastPurpose;
  }

  return identity;
}

/**
 * OCR API client — Issue #314
 * Typed API client for member card reading and handwriting recognition.
 */

export type OcrMode = 'member_card' | 'handwriting';

export interface OcrRequest {
  image_data: string; // JPEG base64 (data:image/jpeg;base64,... or raw)
  mode: OcrMode;
  session_id?: string;
}

export interface OcrResponse {
  success: boolean;
  mode: OcrMode;
  member_number: number | null;
  recognized_text: string | null;
  confidence: number;
  language: string | null;
  expression: string | null;
  processing_time_ms: number;
  visitor_identity: Record<string, unknown> | null;
  error: string | null;
}

export async function submitOcrImage(request: OcrRequest): Promise<OcrResponse> {
  const res = await fetch('/api/ocr', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    throw new Error(`OCR API error: ${res.status}`);
  }

  return res.json();
}

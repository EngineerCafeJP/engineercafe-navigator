import { z } from 'zod';

/** Body for `POST /api/voice/filler` (frontend proxy → backend `/api/voice/filler`). */
export const fillerRequestSchema = z.object({
  query: z.string().min(1).max(2000),
  language: z.enum(['ja', 'en', 'zh', 'ko']),
  sessionId: z.string().optional(),
});

export type FillerRequestInput = z.infer<typeof fillerRequestSchema>;

import type { PresentationCompleteReason } from '../presentation-types';

export interface ReceptionPdfGuideProps {
  language: 'ja' | 'en';
  rotateLandscapeHint: string;
  autoStartKey?: number;
  className?: string;
  /** Passed to PiperPlus `/api/voice` narration. */
  sessionId?: string;
  onVisemeControl?: ((viseme: string, intensity: number) => void) | null;
  onExpressionControl?: ((expression: string, weight: number) => void) | null;
  volume?: number;
  onPresentationComplete?: (reason: PresentationCompleteReason) => void;
}

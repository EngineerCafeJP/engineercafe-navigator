import { VRM } from '@pixiv/three-vrm';
import { VRMUtils } from './vrm-utils-core';
import type { ExpressionData } from './expression-controller';
import type { LipSyncFrame } from './lip-sync-analyzer';

// VRM BlendShape Controller for Lip-sync and Expressions
export class VRMBlendShapeController {
  private vrm: VRM;
  private currentViseme: string = 'neutral';
  private currentExpression: Record<string, number> = { neutral: 1.0 };
  private animationFrame: number | null = null;

  constructor(vrm: VRM) {
    this.vrm = vrm;
  }

  /**
   * Set facial expression
   */
  setExpression(expressionName: string, weight: number): void {
    if (!this.vrm.expressionManager) {
      console.warn('VRM expressionManager not available');
      return;
    }

    try {
      const clampedWeight = Math.max(0, Math.min(1, weight));
      // Use expressionManager.setValue() as the single source of truth.
      // Reading via expression objects' .weight can drift from the actual applied value depending on VRM version.
      this.vrm.expressionManager.setValue(expressionName, clampedWeight);
    } catch (error) {
      console.warn(`Error setting expression "${expressionName}":`, error);
    }
  }

  /**
   * Set multiple expressions at once
   */
  setExpressions(expressions: Record<string, number>): void {
    Object.entries(expressions).forEach(([name, weight]) => {
      this.setExpression(name, weight);
    });
    this.currentExpression = { ...expressions };
  }

  /**
   * Set viseme for lip-sync
   */
  setViseme(viseme: string, intensity: number = 1.0): void {
    if (!this.vrm.expressionManager) return;

    // Clear previous viseme
    if (this.currentViseme && this.currentViseme !== viseme) {
      this.setExpression(this.currentViseme, 0);
    }

    // Set new viseme
    this.setExpression(viseme, intensity);
    this.currentViseme = viseme;
  }

  /**
   * Apply lip-sync frame data
   */
  applyLipSyncFrame(frame: LipSyncFrame): void {
    const vrmViseme = VRMUtils.visemeMapping[frame.mouthShape as keyof typeof VRMUtils.visemeMapping] || 'neutral';

    this.setViseme(vrmViseme, frame.mouthOpen);
  }

  /**
   * Apply expression data
   */
  applyExpressionData(expressionData: ExpressionData): void {
    // ExpressionData型はRecord<string, number>と互換性があるため、型ガードで安全性を担保
    if (expressionData && typeof expressionData === 'object') {
      const record: Record<string, number> = {};
      for (const key in expressionData) {
        if (typeof (expressionData as any)[key] === 'number') {
          record[key] = (expressionData as any)[key];
        }
      }
      this.setExpressions(record);
    } else {
      console.warn('Invalid expressionData:', expressionData);
    }
  }

  /**
   * Start automatic blinking
   */
  startAutoBlink(): () => void {
    let blinkTimeout: NodeJS.Timeout;

    const scheduleNextBlink = () => {
      const nextBlinkTime = 2000 + Math.random() * 4000; // 2-6 seconds
      blinkTimeout = setTimeout(() => {
        this.performBlink();
        scheduleNextBlink();
      }, nextBlinkTime);
    };

    scheduleNextBlink();

    // Return cleanup function
    return () => {
      if (blinkTimeout) {
        clearTimeout(blinkTimeout);
      }
    };
  }

  /**
   * Perform a single blink animation
   */
  private performBlink(): void {
    if (!this.vrm.expressionManager) return;

    // Quick blink
    this.setExpression('blink', 1.0);

    setTimeout(() => {
      this.setExpression('blink', 0.0);
    }, 150);
  }

  /**
   * Animate expression transition
   */
  animateToExpression(
    targetExpression: Record<string, number>,
    duration: number = 1000,
  ): Promise<void> {
    return new Promise((resolve) => {
      const startTime = Date.now();
      const startExpression = { ...this.currentExpression };

      const animate = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Ease-out animation
        const easeProgress = 1 - Math.pow(1 - progress, 3);

        // Interpolate expressions
        const currentFrame: Record<string, number> = {};

        // Handle existing expressions
        Object.keys(startExpression).forEach(key => {
          const start = startExpression[key] || 0;
          const target = targetExpression[key] || 0;
          currentFrame[key] = start + (target - start) * easeProgress;
        });

        // Handle new expressions
        Object.keys(targetExpression).forEach(key => {
          if (!(key in startExpression)) {
            currentFrame[key] = targetExpression[key] * easeProgress;
          }
        });

        this.setExpressions(currentFrame);

        if (progress < 1) {
          this.animationFrame = requestAnimationFrame(animate);
        } else {
          this.currentExpression = { ...targetExpression };
          resolve();
        }
      };

      if (this.animationFrame) {
        cancelAnimationFrame(this.animationFrame);
      }

      animate();
    });
  }

  /**
   * Reset all expressions to neutral
   */
  resetToNeutral(): void {
    if (!this.vrm.expressionManager) return;

    // Get all available expressions and set them to 0
    const expressions = this.vrm.expressionManager.expressions;
    expressions.forEach(expression => {
      expression.weight = 0;
    });

    // Set neutral to 1
    this.setExpression('neutral', 1.0);
    this.currentExpression = { neutral: 1.0 };
    this.currentViseme = 'neutral';
  }

  /**
   * Get available expressions
   */
  getAvailableExpressions(): string[] {
    if (!this.vrm.expressionManager) return [];

    return this.vrm.expressionManager.expressions.map(expr => expr.expressionName);
  }

  /**
   * Get current expression weights
   */
  getCurrentExpressions(): Record<string, number> {
    if (!this.vrm.expressionManager) return {};

    const current: Record<string, number> = {};
    this.vrm.expressionManager.expressions.forEach((expr) => {
      current[expr.expressionName] = this.vrm.expressionManager?.getValue(expr.expressionName) ?? 0;
    });

    return current;
  }

  dispose(): void {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
    }
  }
}

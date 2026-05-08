export interface SlideEventDetail {
  slideNumber: number;
  sessionId?: string;
  narrationRunId?: number;
}

export class SlideEventManager extends EventTarget {
  emitSlideTransitionStart(
    slideNumber: number,
    detail: Omit<SlideEventDetail, 'slideNumber'> = {},
  ): void {
    this.dispatchEvent(new CustomEvent<SlideEventDetail>('slideTransitionStart', {
      detail: { slideNumber, ...detail }
    }));
  }

  emitSlideTransitionComplete(
    slideNumber: number,
    detail: Omit<SlideEventDetail, 'slideNumber'> = {},
  ): void {
    this.dispatchEvent(new CustomEvent<SlideEventDetail>('slideTransitionComplete', {
      detail: { slideNumber, ...detail }
    }));
  }

  emitNarrationStart(
    slideNumber: number,
    detail: Omit<SlideEventDetail, 'slideNumber'> = {},
  ): void {
    this.dispatchEvent(new CustomEvent<SlideEventDetail>('narrationStart', {
      detail: { slideNumber, ...detail }
    }));
  }

  emitNarrationComplete(
    slideNumber: number,
    detail: Omit<SlideEventDetail, 'slideNumber'> = {},
  ): void {
    this.dispatchEvent(new CustomEvent<SlideEventDetail>('narrationComplete', {
      detail: { slideNumber, ...detail }
    }));
  }
}

export const slideEventManager = new SlideEventManager();

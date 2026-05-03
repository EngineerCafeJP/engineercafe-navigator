import { webcrypto } from 'node:crypto';

if (!globalThis.CustomEvent) {
  globalThis.CustomEvent = class CustomEvent<T = unknown> extends Event {
    readonly detail: T;

    constructor(type: string, eventInitDict: CustomEventInit<T> = {}) {
      super(type, eventInitDict);
      this.detail = eventInitDict.detail as T;
    }

    initCustomEvent(): void {
      // Legacy DOM API shape required by TypeScript's CustomEvent interface.
    }
  } as typeof CustomEvent;
}

if (!globalThis.crypto) {
  Object.defineProperty(globalThis, 'crypto', {
    value: webcrypto,
    configurable: true,
  });
}

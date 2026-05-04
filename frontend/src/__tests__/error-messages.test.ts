import assert from "node:assert/strict";
import { test } from "node:test";

import { formatError } from "../lib/error-messages";

test("formatError preserves Safari microphone permission failures by DOMException name", () => {
  const error = Object.assign(new Error("Permission denied"), {
    name: "NotAllowedError",
    originalName: "NotAllowedError",
  });

  assert.match(formatError(error, "ja"), /マイク.*許可/);
  assert.match(formatError(error, "en"), /Microphone permission is required/);
});

test("formatError maps microphone device and state failures to actionable messages", () => {
  assert.match(
    formatError(
      Object.assign(new Error("missing"), { name: "NotFoundError" }),
      "ja",
    ),
    /見つかりません/,
  );
  assert.match(
    formatError(
      Object.assign(new Error("busy"), { name: "NotReadableError" }),
      "ja",
    ),
    /他のアプリ/,
  );
  assert.match(
    formatError(
      Object.assign(new Error("state"), { name: "InvalidStateError" }),
      "ja",
    ),
    /マイクボタン/,
  );
});

test("formatError maps backend timeout to a voice warmup message", () => {
  assert.match(
    formatError(Object.assign(new Error("Backend request timed out"), { status: 504 }), "ja"),
    /起動に時間/,
  );
  assert.match(
    formatError(Object.assign(new Error("Backend request timed out"), { status: 504 }), "en"),
    /warming up/,
  );
});

test("formatError uses MIC_NOT_FOUND_IOS copy on iOS for NotFoundError", () => {
  const prev = globalThis.navigator;
  Object.defineProperty(globalThis, "navigator", {
    value: {
      userAgent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
      maxTouchPoints: 5,
    },
    configurable: true,
  });
  try {
    assert.match(
      formatError(Object.assign(new Error("missing"), { name: "NotFoundError" }), "ja"),
      /画面録画/,
    );
    assert.match(
      formatError(Object.assign(new Error("missing"), { name: "NotFoundError" }), "en"),
      /Settings → Safari/,
    );
  } finally {
    if (prev === undefined) {
      Reflect.deleteProperty(globalThis, "navigator");
    } else {
      Object.defineProperty(globalThis, "navigator", {
        value: prev,
        configurable: true,
        writable: true,
      });
    }
  }
});

test("formatError keeps MIC_NOT_FOUND on Android and desktop for NotFoundError", () => {
  const prev = globalThis.navigator;
  const cases = [
    {
      userAgent:
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
      maxTouchPoints: 5,
    },
    {
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      maxTouchPoints: 0,
    },
  ];
  for (const nav of cases) {
    Object.defineProperty(globalThis, "navigator", {
      value: nav,
      configurable: true,
    });
    try {
      assert.match(
        formatError(Object.assign(new Error("missing"), { name: "NotFoundError" }), "ja"),
        /ケーブル/,
      );
      assert.match(
        formatError(Object.assign(new Error("missing"), { name: "NotFoundError" }), "en"),
        /Bluetooth/,
      );
    } finally {
      if (prev === undefined) {
        Reflect.deleteProperty(globalThis, "navigator");
      } else {
        Object.defineProperty(globalThis, "navigator", {
          value: prev,
          configurable: true,
          writable: true,
        });
      }
    }
  }
});


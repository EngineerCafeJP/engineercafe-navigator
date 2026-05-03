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

import assert from "node:assert/strict";
import { test } from "node:test";

import { formatError } from "../lib/error-messages";

test("formatError preserves Safari microphone permission failures by DOMException name", () => {
  const error = Object.assign(new Error("Permission denied"), {
    name: "NotAllowedError",
    originalName: "NotAllowedError",
  });

  assert.match(formatError(error, "ja"), /マイク.*拒否/);
  assert.match(formatError(error, "en"), /Microphone access was denied/);
});

test("formatError maps microphone device and state failures to actionable messages", () => {
  assert.match(
    formatError(
      Object.assign(new Error("missing"), { name: "NotFoundError" }),
      "ja",
    ),
    /検出されません/,
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
    /もう一度ボタン/,
  );
});

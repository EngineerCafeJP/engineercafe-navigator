import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { test } from 'node:test';

type VercelConfig = {
  functions?: Record<string, { maxDuration?: number }>;
};

const frontendRoot = path.resolve(__dirname, '..', '..');

async function readText(relativePath: string): Promise<string> {
  return readFile(path.join(frontendRoot, relativePath), 'utf-8');
}

function explicitTimeouts(source: string): number[] {
  const constants = new Map(
    Array.from(source.matchAll(/const\s+([A-Z0-9_]+)\s*=\s*([0-9][0-9_]*)/g)).map(
      (match) => [match[1], Number(match[2].replaceAll('_', ''))] as const,
    ),
  );

  return Array.from(source.matchAll(/timeoutMs:\s*([A-Z0-9_]+|[0-9][0-9_]*)/g)).map(
    (match) => {
      const value = match[1];
      if (/^[0-9]/.test(value)) {
        return Number(value.replaceAll('_', ''));
      }
      const constantValue = constants.get(value);
      assert.equal(
        typeof constantValue,
        'number',
        `timeoutMs constant ${value} must be declared in the same route file`,
      );
      return constantValue as number;
    },
  );
}

test('frontend API proxy timeouts stay below their Vercel maxDuration', async () => {
  const config = JSON.parse(await readText('vercel.json')) as VercelConfig;
  const functions = config.functions ?? {};

  for (const [routePath, settings] of Object.entries(functions)) {
    const maxDurationMs = (settings.maxDuration ?? 0) * 1000;
    assert.ok(maxDurationMs > 0, `${routePath} must declare a positive maxDuration`);

    const sourcePath = routePath.replace(/^src\//, 'src/');
    const source = await readText(sourcePath);

    for (const timeoutMs of explicitTimeouts(source)) {
      assert.ok(
        timeoutMs < maxDurationMs,
        `${routePath} timeoutMs ${timeoutMs} must be below maxDuration ${maxDurationMs}`
      );
    }
  }
});

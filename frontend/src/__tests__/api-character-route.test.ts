import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, test } from 'node:test';
import { NextRequest } from 'next/server';

import { GET } from '../app/api/character/route';

const originalCwd = process.cwd();
let tempDir: string | null = null;

afterEach(async () => {
  process.chdir(originalCwd);

  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = null;
  }
});

test('returns supported feature arrays when manifest is missing', async () => {
  const response = await GET(
    new NextRequest('https://example.com/api/character?action=supported_features')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    success: true,
    expressions: ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'],
    animations: ['idle', 'bowing', 'greeting', 'looking', 'talking', 'thinking'],
  });
});

test('returns manifest animations when a character animation manifest exists', async () => {
  tempDir = await mkdtemp(path.join(os.tmpdir(), 'character-route-'));
  await mkdir(path.join(tempDir, 'public', 'characters', 'animations'), { recursive: true });
  await writeFile(
    path.join(tempDir, 'public', 'characters', 'animations', 'manifest.json'),
    JSON.stringify({
      animations: ['wave', 'bow'],
    })
  );

  process.chdir(tempDir);

  const response = await GET(
    new NextRequest('https://example.com/api/character?action=supported_features')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    success: true,
    expressions: ['neutral', 'happy', 'sad', 'angry', 'relaxed', 'surprised'],
    animations: ['idle', 'bowing', 'greeting', 'looking', 'talking', 'thinking'],
  });
});

test('keeps the default GET health payload for other actions', async () => {
  const response = await GET(
    new NextRequest('https://example.com/api/character?action=current_state')
  );

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    status: 'ok',
  });
});

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { parseReceptionNarrationMarkdown } from '../lib/reception/parse-reception-narration-md';

const frontendRoot = path.resolve(__dirname, '..', '..');
const repoRoot = path.resolve(frontendRoot, '..');
const publicReceptionDir = path.join(frontendRoot, 'public', 'reception');
const backendNarrationDir = path.join(repoRoot, 'backend', 'slides', 'narration');

function countPdfPages(filePath: string): number {
  const text = fs.readFileSync(filePath, 'latin1');
  return text.match(/\/Type\s*\/Page(?!s)/g)?.length ?? 0;
}

function loadBackendNarrationSlides(language: 'ja' | 'en'): unknown[] {
  const filePath = path.join(backendNarrationDir, `engineer-cafe-${language}.json`);
  const data = JSON.parse(fs.readFileSync(filePath, 'utf8')) as { slides?: unknown[] };
  return data.slides ?? [];
}

for (const language of ['ja', 'en'] as const) {
  test(`reception ${language} PDF pages match markdown and backend narration`, () => {
    const pdfPath = path.join(publicReceptionDir, `engineer-cafe-${language}.pdf`);
    const mdPath = path.join(publicReceptionDir, `engineer-cafe-narration-${language}.md`);

    const pdfPageCount = countPdfPages(pdfPath);
    const markdownSlides = parseReceptionNarrationMarkdown(
      fs.readFileSync(mdPath, 'utf8'),
      language,
    );
    const backendSlides = loadBackendNarrationSlides(language);

    assert.equal(pdfPageCount, 5);
    assert.equal(markdownSlides.length, pdfPageCount);
    assert.equal(backendSlides.length, pdfPageCount);
  });
}

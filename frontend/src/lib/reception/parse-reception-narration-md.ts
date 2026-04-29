/** Deterministic parsing for public/reception/engineer-cafe-narration-{ja,en}.md */

export function parseReceptionNarrationMarkdown(
  md: string,
  language: 'ja' | 'en',
): string[] {
  const re =
    language === 'ja'
      ? /## スライド(\d+)[：:][^\n]*\n\n([\s\S]*?)(?=\n---|\n## |$)/g
      : /## Slide (\d+):[^\n]*\n\n([\s\S]*?)(?=\n---|\n## |$)/g;

  const items: { n: number; body: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(md)) !== null) {
    const n = parseInt(m[1], 10);
    const body = m[2].trim().replace(/\n\n/g, '\n');
    items.push({ n, body });
  }
  items.sort((a, b) => a.n - b.n);
  return items.map((x) => x.body);
}

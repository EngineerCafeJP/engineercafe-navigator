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

export interface ReceptionNarrationSlide {
  slideIndex: number;
  text: string;
}

/** Same parser as {@link parseReceptionNarrationMarkdown}, plus explicit slide indices (1-based). */
export function parseReceptionNarrationMarkdownSlides(
  md: string,
  language: 'ja' | 'en',
): ReceptionNarrationSlide[] {
  const re =
    language === 'ja'
      ? /## スライド(\d+)[：:][^\n]*\n\n([\s\S]*?)(?=\n---|\n## |$)/g
      : /## Slide (\d+):[^\n]*\n\n([\s\S]*?)(?=\n---|\n## |$)/g;

  const items: ReceptionNarrationSlide[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(md)) !== null) {
    const slideIndex = parseInt(m[1], 10);
    const body = m[2].trim().replace(/\n\n/g, '\n');
    items.push({ slideIndex, text: body });
  }
  items.sort((a, b) => a.slideIndex - b.slideIndex);
  return items;
}


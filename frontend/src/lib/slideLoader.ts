/**
 * Load a slide deck and its narration in the selected language.
 *
 * Uses fetch so this works on both Node.js and edge/worker runtimes.
 * The markdown and narration files must be served from /slides/ under the
 * public directory (or an equivalent static asset path).
 */
export async function loadSlides(
  baseUrl: string,
  lang: 'ja' | 'en',
  deckName = 'engineer-cafe',
): Promise<{ markdown: string; narration: string[] }> {
  const mdUrl = `${baseUrl}/slides/${lang}/${deckName}.md`;
  const narrationUrl = `${baseUrl}/slides/narration/${deckName}-${lang}.txt`;

  const [mdRes, narrationRes] = await Promise.all([
    fetch(mdUrl),
    fetch(narrationUrl),
  ]);

  if (!mdRes.ok) {
    throw new Error(`Failed to load slide markdown from ${mdUrl}: ${mdRes.status}`);
  }
  if (!narrationRes.ok) {
    throw new Error(
      `Failed to load narration from ${narrationUrl}: ${narrationRes.status}`,
    );
  }

  const markdown = await mdRes.text();
  const narrationText = await narrationRes.text();

  return {
    markdown,
    narration: narrationText
      .split('\n')
      .filter(Boolean)
      .map((l) => l.replace(/^\d+\s/, '')),
  };
}

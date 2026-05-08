export function isSlideAgentMetadata(metadata: unknown): boolean {
  if (!metadata || typeof metadata !== 'object') {
    return false;
  }
  const candidate = metadata as Record<string, unknown>;

  return (
    candidate.agent === 'SlideAgent' ||
    candidate.route === 'slide' ||
    candidate.reception_target_agent === 'slide_agent' ||
    candidate.reception_target_agent === 'SlideAgent'
  );
}

import type { CSSProperties } from 'react';
import type { BackgroundOption } from '@/app/components/BackgroundSelector';

export function getStageBackgroundStyle(background: BackgroundOption): CSSProperties {
  if (background.type === 'image') {
    return {
      backgroundImage: `url(${background.value})`,
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
      backgroundSize: 'cover',
    };
  }

  if (background.type === 'gradient') {
    return { background: background.value };
  }

  return background.value ? { backgroundColor: background.value } : {};
}

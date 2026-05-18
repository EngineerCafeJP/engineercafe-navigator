import * as THREE from 'three';
import type { CSSProperties } from 'react';
import type { BackgroundOption } from './types';

export const parseGradientColors = (color: string): string => {
  // Parse CSS gradient values like "linear-gradient(45deg, #ff0000, #00ff00)"
  const gradientMatch = color.match(/linear-gradient\((.*)\)/);
  if (gradientMatch) {
    const parts = gradientMatch[1].split(',').map(s => s.trim());
    if (parts.length >= 2) {
      // Return the first color from the gradient
      return parts[1].replace(/\s+\d+%?$/, '');
    }
  }
  return color;
};

export const createGradientTexture = (options: BackgroundOption): THREE.Texture => {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 1024;
  const context = canvas.getContext('2d')!;

  // Parse colors if they contain gradient values
  const color1 = parseGradientColors(options.color1 || '#e0e7ff');
  const color2 = parseGradientColors(options.color2 || '#c7d2fe');

  // Calculate gradient angle
  const angle = (options.angle || 0) * Math.PI / 180;
  const x1 = canvas.width / 2 - Math.cos(angle) * canvas.width / 2;
  const y1 = canvas.height / 2 - Math.sin(angle) * canvas.height / 2;
  const x2 = canvas.width / 2 + Math.cos(angle) * canvas.width / 2;
  const y2 = canvas.height / 2 + Math.sin(angle) * canvas.height / 2;

  const gradient = context.createLinearGradient(x1, y1, x2, y2);
  gradient.addColorStop(0, color1);
  gradient.addColorStop(1, color2);

  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
};

/** Normalize BackgroundSelector-style option (gradient value as CSS) to scene format */
export const normalizeBackgroundForScene = (options: BackgroundOption): BackgroundOption => {
  if (options.type !== 'gradient' || options.color1) return options;
  const css = options.value || '';
  const angleMatch = css.match(/(\d+)deg/);
  const angle = angleMatch ? Number(angleMatch[1]) : 135;
  const colorMatches = css.match(/#[0-9a-fA-F]{6}|rgb\([^)]+\)|rgba\([^)]+\)/g);
  const color1 = colorMatches?.[0] ?? '#e0e7ff';
  const color2 = colorMatches?.[colorMatches.length - 1] ?? '#c7d2fe';
  return { ...options, color1, color2, angle };
};

export const getFallbackSurfaceStyle = (background?: BackgroundOption): CSSProperties => {
  const bg =
    background ?? {
      type: 'gradient' as const,
      color1: '#e0e7ff',
      color2: '#c7d2fe',
      angle: 135,
    };
  const normalized = normalizeBackgroundForScene(bg);
  if (normalized.type === 'solid') {
    const color = parseGradientColors(normalized.color1 || normalized.value || '#f5f5f5');
    return { backgroundColor: color };
  }
  if (normalized.type === 'gradient') {
    const c1 = normalized.color1 || '#e0e7ff';
    const c2 = normalized.color2 || '#c7d2fe';
    const angle = normalized.angle ?? 135;
    return { background: `linear-gradient(${angle}deg, ${c1}, ${c2})` };
  }
  if (normalized.type === 'image' && (normalized.imageUrl || normalized.value)) {
    const url = normalized.imageUrl || normalized.value || '';
    return {
      backgroundImage: `url(${JSON.stringify(url)})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
    };
  }
  return { background: 'linear-gradient(135deg, #e0e7ff, #c7d2fe)' };
};

export const updateThreeSceneBackground = (
  scene: THREE.Scene | null,
  options: BackgroundOption,
) => {
  if (!scene) return;

  // Dispose of previous background texture if it exists
  const previousBackground = scene.background;
  if (previousBackground instanceof THREE.Texture) {
    previousBackground.dispose();
  }

  const normalized = normalizeBackgroundForScene(options);
  if (normalized.type === 'solid') {
    const color = parseGradientColors(normalized.color1 || normalized.value || '#f5f5f5');
    scene.background = new THREE.Color(color);
  } else if (normalized.type === 'gradient') {
    scene.background = createGradientTexture(normalized);
  } else if (normalized.type === 'image' && (normalized.imageUrl || normalized.value)) {
    const loader = new THREE.TextureLoader();
    const imageUrl = normalized.imageUrl || normalized.value || '';
    if (imageUrl) {
      loader.load(
        imageUrl,
        (texture) => {
          texture.colorSpace = THREE.SRGBColorSpace;
          if (scene) {
            const prev = scene.background;
            if (prev instanceof THREE.Texture) {
              prev.dispose();
            }
            scene.background = texture;
          }
        },
        undefined,
        (error) => {
          console.error('Error loading background image:', error);
          scene.background = new THREE.Color('#f5f5f5');
        },
      );
    }
  } else {
    scene.background = new THREE.Color('#f5f5f5');
  }
};

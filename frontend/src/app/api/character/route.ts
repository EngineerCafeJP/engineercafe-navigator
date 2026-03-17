import { readFile } from 'node:fs/promises';
import path from 'node:path';

import { NextRequest, NextResponse } from 'next/server';

import { backendFetch } from '@/lib/api/backend-proxy';

const DEFAULT_SUPPORTED_EXPRESSIONS = [
  'neutral',
  'happy',
  'sad',
  'angry',
  'relaxed',
  'surprised',
];

const DEFAULT_SUPPORTED_ANIMATIONS = [
  'idle',
  'bowing',
  'greeting',
  'looking',
  'talking',
  'thinking',
];

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((entry) => typeof entry === 'string');

async function getSupportedAnimations() {
  const manifestPath = path.join(
    process.cwd(),
    'public',
    'characters',
    'animations',
    'manifest.json'
  );

  try {
    const manifestContent = await readFile(manifestPath, 'utf-8');
    const manifest = JSON.parse(manifestContent) as unknown;

    if (isStringArray(manifest)) {
      return manifest;
    }

    if (
      manifest &&
      typeof manifest === 'object' &&
      'animations' in manifest &&
      isStringArray(manifest.animations)
    ) {
      return manifest.animations;
    }

    console.warn('[character route] Unsupported animation manifest format:', manifestPath);
  } catch (error) {
    const code = error && typeof error === 'object' && 'code' in error ? error.code : null;

    if (code !== 'ENOENT') {
      console.warn('[character route] Failed to load animation manifest:', error);
    }
  }

  return DEFAULT_SUPPORTED_ANIMATIONS;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await backendFetch('/api/character', {
      body,
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.status}`);
    }

    return NextResponse.json(response.data);
  } catch (error) {
    console.error('Character API error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        ...(process.env.NODE_ENV === 'development' && {
          details: error instanceof Error ? error.message : 'Unknown error',
        }),
      },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  const action = request.nextUrl.searchParams.get('action');

  if (action === 'supported_features') {
    const animations = await getSupportedAnimations();

    return NextResponse.json({
      success: true,
      expressions: DEFAULT_SUPPORTED_EXPRESSIONS,
      animations,
    });
  }

  return NextResponse.json({
    status: 'ok',
  });
}

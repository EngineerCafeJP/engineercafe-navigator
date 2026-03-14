import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    const origin = new URL(request.url).origin;
    const res = await fetch(`${origin}/backgrounds/manifest.json`);

    if (!res.ok) {
      return NextResponse.json({ images: [], total: 0 });
    }

    const files: string[] = await res.json();

    const imageFiles = files.filter(
      (file) =>
        /\.(jpg|jpeg|png|webp|svg)$/i.test(file) &&
        !file.startsWith('.') &&
        !file.toLowerCase().includes('readme'),
    );

    return NextResponse.json({
      images: imageFiles,
      total: imageFiles.length,
    });
  } catch {
    return NextResponse.json({
      images: [],
      error: 'Failed to read backgrounds manifest',
    });
  }
}

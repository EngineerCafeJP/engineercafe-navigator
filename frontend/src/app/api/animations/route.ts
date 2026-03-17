import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    const origin = new URL(request.url).origin;
    const res = await fetch(`${origin}/animations/manifest.json`);

    if (!res.ok) {
      return NextResponse.json({ animations: [], total: 0 });
    }

    const files: string[] = await res.json();

    const animationFiles = files.filter(
      (file) =>
        /\.vrma$/i.test(file) &&
        !file.startsWith('.') &&
        !file.toLowerCase().includes('readme'),
    );

    return NextResponse.json({
      animations: animationFiles,
      total: animationFiles.length,
    });
  } catch {
    return NextResponse.json({
      animations: [],
      error: 'Failed to read animations manifest',
    });
  }
}

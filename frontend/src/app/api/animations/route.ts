import { NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

export async function GET() {
  try {
    const animations_dir = path.join(process.cwd(), 'public', 'animations');

    try {
      await fs.access(animations_dir);
    } catch {
      return NextResponse.json({ animations: [] });
    }

    const files = await fs.readdir(animations_dir);

    const vrma_files = files.filter(
      (file) =>
        file.toLowerCase().endsWith('.vrma') &&
        !file.startsWith('.') &&
        !file.toLowerCase().includes('readme')
    );

    const animations = vrma_files.map((file) => {
      const base_name = file.replace(/\.vrma$/i, '');
      const label =
        base_name
          .split(/[-_]/)
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
          .join(' ') || base_name;
      return {
        value: `/animations/${file}`,
        label,
      };
    });

    return NextResponse.json({ animations });
  } catch (error) {
    console.error('Error reading animations directory:', error);
    return NextResponse.json({
      animations: [],
      error: 'Failed to read animations directory',
    });
  }
}

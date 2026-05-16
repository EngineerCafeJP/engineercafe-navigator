import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Engineer Cafe Navigator',
  description: '福岡市エンジニアカフェの音声AIエージェントシステム',
  keywords: ['エンジニアカフェ', 'Engineer Cafe', 'AI', '音声案内', 'Fukuoka'],
  authors: [{ name: 'Engineer Cafe Team' }],
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  minimumScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  interactiveWidget: 'overlays-content',
  themeColor: '#3B82F6',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <head>
        <link rel="icon" href="/assets/images/favicon.ico" />
      </head>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}

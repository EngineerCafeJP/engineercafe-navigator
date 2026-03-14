# Engineer Cafe Navigator - Frontend

> Next.js 15 + TypeScript + React 19 フロントエンドアプリケーション

English version: [../README-EN.md](../README-EN.md) (monorepo overview)

[![Next.js](https://img.shields.io/badge/Next.js-15.3.2-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8.3-blue)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React-19.1.0-61dafb)](https://reactjs.org/)
[![Three.js](https://img.shields.io/badge/Three.js-VRM-orange)](https://threejs.org/)

## 概要

エンジニアカフェナビゲーターのフロントエンドアプリケーション。UIとユーザーインタラクションを担当し、AIロジックはバックエンド（LangGraph）に委譲します。

**主要機能:**
- 音声AIエージェントインターフェース
- VRMキャラクター表示（Three.js + @pixiv/three-vrm）
- リアルタイム会話
- スライドプレゼンテーション（Marp）
- 多言語対応（日本語・英語）

## セットアップ

### 前提条件

- Node.js >= 18.0.0
- pnpm >= 8.0.0

### インストール

```bash
cd frontend
pnpm install
```

### 環境変数

`.env.local` を作成:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GOOGLE_CLOUD_PROJECT_ID=your-gcp-project-id
GOOGLE_CLOUD_CREDENTIALS=./config/service-account-key.json
GOOGLE_GENERATIVE_AI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
```

### 開発サーバー

```bash
pnpm dev          # http://localhost:3000
pnpm dev:clean    # キャッシュクリア後に起動
```

## コマンド

```bash
# 開発
pnpm dev                    # 開発サーバー起動
pnpm build                  # プロダクションビルド（opennextjs-cloudflare）
pnpm start                  # プロダクションサーバー起動

# コード品質
pnpm lint                   # ESLint
pnpm typecheck              # TypeScriptチェック

# テスト
pnpm test                   # テストスイート実行
pnpm test:e2e               # Playwright E2E テスト
pnpm test:e2e:ui            # Playwright UI モード

# デプロイ
pnpm deploy                 # ビルド + Cloudflare Workersにデプロイ
```

## プロジェクト構造

```
frontend/src/
├── app/                          # Next.js App Router
│   ├── api/                      # API Routes
│   │   ├── voice/route.ts        # 音声処理API
│   │   ├── marp/route.ts         # スライドAPI
│   │   ├── character/route.ts    # キャラクターAPI
│   │   ├── slides/route.ts       # スライド操作API
│   │   ├── qa/route.ts           # Q&A API
│   │   └── monitoring/           # 監視・ヘルスチェックAPI
│   ├── components/               # React Components
│   │   ├── AudioControls.tsx     # 音声制御
│   │   ├── BackgroundSelector.tsx # 背景選択
│   │   ├── CharacterAvatar.tsx   # VRMキャラクター表示
│   │   ├── LanguageSelector.tsx  # 言語切り替え
│   │   ├── MarpViewer.tsx        # Marpスライドビューア
│   │   └── VoiceInterface.tsx    # 音声インターフェース
│   ├── globals.css               # グローバルスタイル
│   └── page.tsx                  # メインページ
├── lib/                          # 共通ライブラリ
│   ├── audio/                    # 統一音声システム（Web Audio API専用）
│   │   ├── audio-playback-service.ts  # 統一音声再生サービス
│   │   ├── web-audio-player.ts   # Web Audio APIプレイヤー
│   │   └── mobile-audio-service.ts # モバイル対応
│   ├── marp-processor.ts         # Marp処理
│   ├── simplified-memory.ts      # メモリシステム
│   ├── stt-correction.ts         # STT誤認識補正
│   ├── lip-sync-analyzer.ts      # リップシンク解析
│   └── supabase.ts              # Supabase設定
├── mastra/                       # Mastra設定（バックエンドLangGraphに移行中）
│   ├── agents/                   # AIエージェント
│   ├── workflows/                # ワークフロー
│   └── tools/                    # Mastra Tools
├── slides/                       # スライドコンテンツ
│   ├── engineer-cafe.md          # メインスライド
│   ├── themes/                   # カスタムテーマ
│   └── narration/                # ナレーションJSON
└── types/                        # 型定義
```

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| フレームワーク | Next.js 15.3.2 + React 19.1.0 |
| 言語 | TypeScript 5.8.3 |
| スタイリング | Tailwind CSS v3.4.17 |
| 3Dキャラクター | Three.js 0.176.0 + @pixiv/three-vrm 3.4.0 |
| スライド | Marp Core 4.1.0 |
| 音声 | Web Audio API（HTMLAudioElement不使用） |
| デプロイ | Cloudflare Workers（opennextjs-cloudflare） |

## 重要な制約

### Tailwind CSS v3

**Tailwind CSS v4 にアップグレードしないでください。** v4 には破壊的変更があります。

```bash
# 正しいバージョン
pnpm add -D tailwindcss@3.4.17 postcss@8.4.47 autoprefixer@10.4.20
```

PostCSS設定では `tailwindcss: {}` を使用（`@tailwindcss/postcss: {}` ではありません）。

### 音声システム

全音声再生は Web Audio API 経由（`src/lib/audio/`）。HTMLAudioElement は使用禁止。

### VRMモデル

VRMファイルを `public/characters/models/` に配置:

```
public/characters/models/
└── sakura.vrm              # メインガイドキャラクター
```

## トラブルシューティング

### 音声認識が動作しない
- ブラウザのマイクアクセス許可を確認
- HTTPS環境であることを確認（localhostはHTTPでも可）
- Google Cloud Speech APIが有効化されているか確認

### キャラクターが表示されない
- `public/characters/models/` にVRMファイルがあるか確認
- ブラウザがWebGLに対応しているか確認

### スライドが表示されない
- `src/slides/` にMarkdownファイルがあるか確認
- テーマファイル（`src/slides/themes/`）が存在するか確認

## 関連ドキュメント

- **[プロジェクト全体README](../README.md)** - モノレポ全体の概要
- **[バックエンドREADME](../backend/README.md)** - Python LangGraphバックエンド
- **[ドキュメント一覧](../docs/README.md)** - 全ドキュメントのインデックス
- **[API仕様書](../docs/api/API.md)** - REST API仕様
- **[開発ガイド](../docs/development/DEVELOPER-GUIDE.md)** - 開発者向け技術仕様

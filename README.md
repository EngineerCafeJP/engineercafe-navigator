# Engineer Cafe Navigator

> 福岡市エンジニアカフェの音声AIエージェントシステム（モノレポ構成）

**[🇺🇸 English](README-EN.md)** | **🇯🇵 日本語**

[![Next.js](https://img.shields.io/badge/Next.js-15.3.2-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8.3-blue)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.0-blue)](https://langchain-ai.github.io/langgraph/)
[![Mastra](https://img.shields.io/badge/Mastra-0.10.5-green)](https://mastra.ai/)
[![React](https://img.shields.io/badge/React-19.1.0-61dafb)](https://reactjs.org/)

## 📖 プロジェクト概要

Engineer Cafe Navigator（エンジニアカフェナビゲーター）は、福岡市エンジニアカフェの新規顧客対応を自動化する**多言語対応音声AIエージェントシステム**です。

このプロジェクトは**モノレポ構成**で、以下の2つの主要コンポーネントで構成されています：

- **Frontend (NextJS)**: TypeScript/Reactベースのフロントエンドアプリケーション
- **Backend (Python)**: LangGraphを使用したAIエージェントバックエンド

## 🏗️ プロジェクト構造

```
engineer-cafe-navigator2025/
├── frontend/              # NextJSフロントエンド
│   ├── src/              # ソースコード
│   ├── public/           # 静的ファイル
│   ├── package.json      # Node.js依存関係
│   └── ...
├── backend/              # Python LangGraphバックエンド
│   ├── main.py           # FastAPIアプリケーション
│   ├── workflows/        # LangGraphワークフロー
│   ├── agents/           # エージェント実装
│   ├── requirements.txt  # Python依存関係
│   └── ...
├── package.json          # ルートレベルのワークスペース設定
└── README.md
```

## 🚀 クイックスタート

### 前提条件

- Node.js >= 18.0.0
- pnpm >= 8.0.0
- Python >= 3.11.0
- pip または poetry

### セットアップ

1. **リポジトリのクローン**

```bash
git clone https://github.com/EngineerCafeJP/engineercafe-navigator.git
cd engineercafe-navigator
```

2. **依存関係のインストール**

```bash
# すべての依存関係をインストール
pnpm install

# または個別にインストール
pnpm install:frontend  # NextJSフロントエンド
pnpm install:backend   # Pythonバックエンド
```

3. **環境変数の設定**

**Frontend (.env.local)**
```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
# その他の環境変数...
```

**Backend (.env)**
```env
# backend/.env
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

4. **開発サーバーの起動**

```bash
# フロントエンドとバックエンドを同時に起動
pnpm dev

# または個別に起動
pnpm dev:frontend  # http://localhost:3000
pnpm dev:backend   # http://localhost:8000
```

## 📚 各コンポーネントの詳細

### Frontend (NextJS)

NextJSベースのフロントエンドアプリケーション。Mastraフレームワークを使用してAIエージェント機能を提供します。

**主要機能:**
- 音声AIエージェントインターフェース
- VRMキャラクター表示
- リアルタイム会話
- スライドプレゼンテーション

**詳細:** [frontend/README.md](frontend/README.md)

### Backend (Python LangGraph)

Python版LangGraphを使用したAIエージェントバックエンド。FastAPIでRESTful APIを提供します。

**主要機能:**
- LangGraphワークフローによるエージェント実行
- 複数エージェントのルーティング
- 会話メモリ管理
- RAG（Retrieval-Augmented Generation）統合

**詳細:** [backend/README.md](backend/README.md)

## 🆕 最新アップデート

### ✅ LangGraph統合（2025/01/XX）

- **🔗 モノレポ構造への移行** - Frontend（NextJS）とBackend（Python LangGraph）を分離
- **📊 Python版LangGraphワークフロー** - 既存のMastraエージェントロジックをPython版LangGraphで実装
- **🔄 FastAPIバックエンド** - RESTful APIによるフロントエンドとバックエンドの統合
- **💾 グラフベースのワークフロー** - より柔軟なルーティングと状態管理
- **🔄 永続的な実行** - 失敗から自動的に回復し、長時間実行可能

## 🛠️ 開発

### フロントエンド開発

```bash
cd frontend
pnpm dev
```

### バックエンド開発

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### テスト

```bash
# フロントエンドテスト
pnpm test:frontend

# バックエンドテスト
pnpm test:backend
```

## 📦 ビルド

```bash
# フロントエンドのビルド
pnpm build:frontend

# 本番環境用のビルド
cd frontend && pnpm build
```

## 🔧 技術スタック

### Frontend
- **Framework**: Next.js 15.3.2
- **Language**: TypeScript 5.8.3
- **UI**: React 19.1.0
- **AI Framework**: Mastra 0.10.5
- **3D**: Three.js + VRM

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **AI Framework**: LangGraph 0.2.0
- **LLM**: LangChain (OpenAI, Google Gemini)

## 📖 ドキュメント

- [開発者ガイド](docs/DEVELOPMENT.md)
- [API ドキュメント](docs/API.md)
- [システムアーキテクチャ](docs/SYSTEM-ARCHITECTURE.md)
- [デプロイメントガイド](docs/DEPLOYMENT.md)

## 🤝 コントリビューション

コントリビューションを歓迎します！詳細は[CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。

## 📄 ライセンス

ISC License

## 🙏 謝辞

- [LangGraph](https://github.com/langchain-ai/langgraph) - AIエージェントワークフロー
- [Mastra](https://mastra.ai/) - AIフレームワーク
- [Next.js](https://nextjs.org/) - Reactフレームワーク

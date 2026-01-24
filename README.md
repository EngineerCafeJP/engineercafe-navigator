# Engineer Cafe Navigator

> 福岡市エンジニアカフェの音声AIエージェントシステム（モノレポ構成）

**[🇺🇸 English](README-EN.md)** | **🇯🇵 日本語**

[![Next.js](https://img.shields.io/badge/Next.js-15.3.2-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8.3-blue)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.0-blue)](https://langchain-ai.github.io/langgraph/)
[![LangSmith](https://img.shields.io/badge/LangSmith-Evaluation-orange)](https://smith.langchain.com/)
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

**推奨: Docker環境**
- Docker Desktop
- Docker Compose

**または、ローカル環境**
- mise (バージョン管理ツール)
- Node.js >= 18.0.0
- pnpm >= 8.0.0
- Python >= 3.11.0

### 🐳 Docker環境でのセットアップ（推奨）

1. **リポジトリのクローン**

```bash
git clone https://github.com/EngineerCafeJP/engineercafe-navigator.git
cd engineercafe-navigator
```

2. **環境変数の設定**

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

3. **初回セットアップと起動**

```bash
# Makefileを使った統一コマンド
make setup  # 初回セットアップ（Docker buildを実行）
make dev    # 開発サーバー起動（http://localhost:3000, http://localhost:8000）
```

**その他のコマンド:**
```bash
make help              # 使用可能なコマンド一覧
make dev:frontend      # フロントエンドのみ起動
make dev:backend       # バックエンドのみ起動
make lint              # リンター実行
make clean             # クリーンアップ
```

### 🛠️ ローカル環境でのセットアップ（mise使用）

miseを使用したローカル開発環境の構築:

1. **mise のインストール**

```bash
# macOS (Homebrew)
brew install mise

# または公式サイトから
curl https://mise.run | sh
```

2. **プロジェクトツールのインストール**

```bash
mise install  # Node.js, Python, pnpm を自動インストール
```

3. **依存関係のインストールと起動**

```bash
make install  # 依存関係インストール
make dev      # 開発サーバー起動
```

## 📚 各コンポーネントの詳細

### Frontend (NextJS)

NextJSベースのフロントエンドアプリケーション。UIとユーザーインタラクションを担当し、AIロジックはバックエンド（LangGraph）に委譲します。

> **📌 移行中**: フロントエンドのMastraロジックをLangGraphバックエンドに移行中です。詳細は [Issue #37-42](https://github.com/EngineerCafeJP/engineercafe-navigator/issues) を参照。

**主要機能:**
- 音声AIエージェントインターフェース
- VRMキャラクター表示（Three.js）
- リアルタイム会話
- スライドプレゼンテーション（Marp）

**詳細:** [frontend/README.md](frontend/README.md)

### Backend (Python LangGraph)

Python版LangGraphを使用したAIエージェントバックエンド。FastAPIでRESTful APIを提供します。

**実装済みエージェント（9種）:**
| エージェント | 責務 |
|-------------|------|
| BusinessInfoAgent | 営業時間・料金・アクセス |
| FacilityAgent | 設備・Wi-Fi・地下施設 |
| EventAgent | イベント・カレンダー |
| SlideAgent | スライド表示・ナレーション |
| GeneralKnowledgeAgent | Web検索（範囲外質問） |
| MemoryAgent | 会話履歴・コンテキスト |
| ClarificationAgent | 曖昧解消 |
| VoiceAgent | 音声処理（STT/TTS） |
| CharacterControlAgent | VRM制御 |

**主要機能:**
- LangGraphワークフローによるエージェント実行
- LangSmithによる評価・トレーシング
- 会話メモリ管理（3分TTL）
- Enhanced RAG統合

**詳細:** [backend/README.md](backend/README.md)

## 🆕 最新アップデート

### 🚧 進行中: フロントエンド→LangGraph移行（2026-01）

フロントエンドのクライアントサイド処理をLangGraphバックエンドに移行中：
- **[#37](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/37)** QueryClassifier → RouterAgent
- **[#38](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/38)** EmotionTagger → Agent統一
- **[#39](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/39)** 会話メモリ → LangGraph State
- **[#40](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/40)** フロントエンド薄型化
- **[#42](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/42)** Next.js → Vite移行検討

### ✅ LangGraph統合完了（2026-01-13）

- **🔗 モノレポ構造への移行** - Frontend（NextJS）とBackend（Python LangGraph）を分離 ✅
- **📊 9エージェント実装完了** - 単体テスト62件全パス ✅
- **🔄 FastAPIバックエンド** - RESTful APIによるフロントエンドとバックエンドの統合完了 ✅
- **📈 LangSmith統合** - エージェント評価・トレーシングシステム実装 ✅
- **🧪 テスト基盤整備** - pytest + AsyncMockによる包括的なテストスイート構築 ✅
- **🐳 開発環境整備** - Docker + mise + Makefile による統一開発コマンド整備 ✅
- **🔍 Web検索統合** - Google Gemini API with Search Grounding による最新情報取得 ✅

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
- **3D**: Three.js + @pixiv/three-vrm
- **Styling**: Tailwind CSS v3.4.17

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **AI Framework**: LangGraph 0.2.0
- **LLM**: LangChain (OpenRouter, Google Gemini)
- **Evaluation**: LangSmith
- **Database**: Supabase (PostgreSQL + pgvector)

## 📖 ドキュメント

### 📚 包括的ドキュメント一覧
- **[docs/README.md](docs/README.md)** - 全ドキュメントの一覧と推奨読書順序

### 🚀 クイックスタート
- **[docs/development/AGENT-QUICKSTART.md](docs/development/AGENT-QUICKSTART.md)** - エージェント開発クイックスタート（10分）
- **[docs/development/LOCAL-DEVELOPMENT-SETUP.md](docs/development/LOCAL-DEVELOPMENT-SETUP.md)** - ローカル開発環境セットアップ
- **[docs/development/ENVIRONMENT-VARIABLES.md](docs/development/ENVIRONMENT-VARIABLES.md)** - 環境変数設定ガイド

### 📖 主要ドキュメント
- **[docs/development/DEVELOPER-GUIDE.md](docs/development/DEVELOPER-GUIDE.md)** - 開発者ガイド
- **[docs/api/API.md](docs/api/API.md)** - API ドキュメント
- **[docs/architecture/SYSTEM-ARCHITECTURE.md](docs/architecture/SYSTEM-ARCHITECTURE.md)** - システムアーキテクチャ
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** - デプロイメントガイド
- **[docs/development/TROUBLESHOOTING.md](docs/development/TROUBLESHOOTING.md)** - トラブルシューティング

## 🤝 コントリビューション

コントリビューションを歓迎します！詳細は[CONTRIBUTING.md](docs/development/CONTRIBUTING.md)を参照してください。

## 📄 ライセンス

ISC License

## 🙏 謝辞

- [LangGraph](https://github.com/langchain-ai/langgraph) - AIエージェントワークフロー
- [LangSmith](https://smith.langchain.com/) - エージェント評価・トレーシング
- [Next.js](https://nextjs.org/) - Reactフレームワーク
- [FastAPI](https://fastapi.tiangolo.com/) - Python Webフレームワーク

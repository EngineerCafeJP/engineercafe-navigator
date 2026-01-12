# 📤 Claude Code への依頼: フェーズ8 開発環境整備

## タスク
**フェーズ 8: 開発環境整備（Docker + mise + Makefile）**

各エンジニアが素早くローカルで開発環境を構築できるよう、Docker環境とmise/Makefileによる統一された開発コマンドを整備する。

## 完了条件

### 8.1 mise設定（バージョン管理基盤）
- [ ] `.mise.toml` 作成
  - Node.js >=18.0.0
  - Python >=3.11.0
  - pnpm >=8.0.0
  - Supabase CLI（オプション）
- [ ] `mise install` で全ツールがインストールされることを確認
- [ ] README.mdにmiseセットアップ手順を追加

### 8.2 Docker環境構築
- [ ] `backend/Dockerfile` 作成
  - Python 3.11 ベースイメージ
  - requirements.txt からの依存関係インストール
  - 開発用設定（ホットリロード対応、uvicorn --reload）
  - 本番用設定（マルチステージビルド、オプション）
- [ ] `frontend/Dockerfile` 作成
  - Node.js 18+ ベースイメージ
  - pnpm インストール
  - 依存関係インストール
  - 開発用設定（Next.js dev server）
  - 本番用設定（Next.js build + start、オプション）
- [ ] `docker-compose.yml` 作成（ルート）
  - frontend サービス定義（ポート3000）
  - backend サービス定義（ポート8000）
  - 環境変数設定（.env ファイル連携）
  - ボリュームマウント（ホットリロード用）
  - ネットワーク設定
- [ ] `.dockerignore` 作成（frontend, backend）
  - node_modules, __pycache__ 等の除外設定
- [ ] `docker-compose up` でフロントエンド・バックエンドが起動することを確認
- [ ] ホットリロードが動作することを確認

### 8.3 Makefile作成（統一コマンド）
- [ ] `Makefile` 作成（ルート）
  - `make setup` - 初回セットアップ（mise install + Docker build）
  - `make install` - 依存関係インストール（mise経由）
  - `make dev` - 開発サーバー起動（docker-compose up）
  - `make dev:frontend` - フロントエンドのみ起動
  - `make dev:backend` - バックエンドのみ起動
  - `make build` - ビルド（フロントエンド + バックエンド）
  - `make test` - テスト実行
  - `make lint` - リンター実行（frontend + backend）
  - `make clean` - クリーンアップ（コンテナ停止、ボリューム削除）
  - `make help` - ヘルプ表示
- [ ] `make setup` で初回セットアップが完了することを確認
- [ ] `make dev` で開発環境が起動することを確認

### 8.4 ドキュメント更新
- [ ] `README.md` 更新
  - miseセットアップ手順追加
  - Dockerセットアップ手順追加
  - Makefileコマンド一覧追加
  - クイックスタートガイド更新（Docker環境を推奨）
- [ ] `docs/development/LOCAL-DEVELOPMENT-SETUP.md` 更新
  - Docker環境のセットアップ手順追加
  - miseの使い方追加
  - Makefileの使い方追加
- [ ] `.gitignore` 確認・更新
  - Docker関連ファイルの除外確認（不要なファイルのみ）
  - mise関連ファイルの除外確認（.mise/ ディレクトリなど）

### CI/CD チェック
- [ ] `pnpm lint` (frontend) - ESLint
- [ ] `pnpm typecheck` (frontend) - TypeScript
- [ ] `pnpm build` (frontend) - Next.js ビルド
- [ ] `ruff check .` (backend) - Python リンター
- [ ] `black --check .` (backend) - Python フォーマット
- [ ] Dockerビルドが成功することを確認（CI/CDで）

### PR作成
- [ ] developブランチにPR作成
- [ ] PR説明に実装内容を記載
- [ ] CI/CDオールグリーン確認

## 参照ファイル

### 既存設定ファイル
- `package.json` (ルート) - 既存のdevスクリプト確認
- `backend/pyproject.toml` - Python設定確認
- `backend/requirements.txt` - Python依存関係確認
- `frontend/package.json` - Next.js設定確認
- `backend/main.py` - FastAPIアプリケーション（ポート8000、CORS設定確認）
- `frontend/next.config.js` - Next.js設定確認
- `.gitignore` - 除外設定確認

### ドキュメント
- `README.md` - メインREADME
- `docs/development/LOCAL-DEVELOPMENT-SETUP.md` - ローカル開発環境セットアップガイド
- `Plans.md` - フェーズ8の詳細仕様

## コンテキスト

### プロジェクト構成
- **モノレポ構成**: frontend/ (Next.js) + backend/ (Python FastAPI)
- **フロントエンド**: Next.js 15.3.2, TypeScript, pnpm
- **バックエンド**: Python 3.11+, FastAPI, LangGraph, uvicorn
- **既存の開発コマンド**: `pnpm dev` (concurrentlyでfrontend/backend同時起動)

### 環境変数
- **Frontend**: `frontend/.env.local` (NEXT_PUBLIC_API_URL, Supabase設定等)
- **Backend**: `backend/.env` (OPENAI_API_KEY, SUPABASE_URL等)

### ポート設定
- **Frontend**: localhost:3000
- **Backend**: localhost:8000
- **CORS**: backend/main.pyでlocalhost:3000, 3001を許可

### 注意点
- Docker環境は既存のローカル環境と競合する可能性がある（ポート3000, 8000）
- miseは既存のNode.js/Python環境と競合しないよう、PATH設定に注意
- Makefileは各OS（macOS, Linux, Windows）で動作するよう配慮（WindowsはWSL2推奨）
- ホットリロードが必須（開発効率のため）

## 実装の優先順位

1. **8.1 mise設定** → バージョン管理の基盤を整備
2. **8.2 Docker環境構築** → 開発環境の統一
3. **8.3 Makefile作成** → 統一コマンドの提供
4. **8.4 ドキュメント更新** → 使い方の明文化

## 実行コマンド（実装後の確認用）

```bash
# mise設定確認
mise install
mise exec -- node --version
mise exec -- python --version
mise exec -- pnpm --version

# Docker環境確認
docker-compose build
docker-compose up -d
docker-compose ps
docker-compose logs frontend
docker-compose logs backend

# Makefile確認
make help
make setup
make dev

# CI/CD確認
cd frontend && pnpm lint && pnpm typecheck && pnpm build
cd backend && ruff check . && black --check .
```

## 完了後

`/handoff-to-cursor` で報告してください。

報告内容:
- 実装完了したファイル一覧
- 動作確認結果
- CI/CD結果
- PR番号とURL
- 注意点・リスク（あれば）

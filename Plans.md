# Plans.md - Engineer Cafe Navigator

> 最終更新: 2025-01-12
> モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 現在のステータス

| 項目 | 状態 |
|------|------|
| **CI/CD** | ✅ グリーン (最終実行: 2025-01-12) |
| **オープン PR** | PR #24 (テスト基盤), PR #25 (バックエンド統合 - Draft) |
| **完了したフェーズ** | 0.5 (OpenRouter), 0.6 (構造整理), 1.1-1.5 (Agent移行), 2.1-2.3 (会話機能骨組み), 6 (テスト), 7.1-7.6 (バックエンド統合) |
| **次のフェーズ** | 7.5 (バックエンド完全実装), 3.1-3.2 (出力機能), 4.1-4.3 (新機能) |
| **ベースブランチ** | develop |

---

## CI/CD チェックリスト

Claude Code は PR 作成・更新時に以下を確認:

- [ ] `pnpm lint` (frontend) - ESLint
- [ ] `pnpm typecheck` (frontend) - TypeScript
- [ ] `pnpm build` (frontend) - Next.js ビルド
- [ ] `ruff check .` (backend) - Python リンター
- [ ] `black --check .` (backend) - Python フォーマット

**失敗時のアクション:**
1. エラーログを確認
2. 自動修正を試行
3. 修正不可の場合は PM に報告

---

---

## フェーズ 1: LangGraph 移行 - コア機能 `cc:DONE`

> 担当: テリスケ, Natsumi, けいてぃー
> **完了**: フェーズ1のコア機能実装は全て完了。詳細はアーカイブ参照。

---

## フェーズ 2: LangGraph 移行 - 会話機能 `cc:DONE`

> 担当: テリスケ（骨組み）, takegg0311・YukitoLyn（完全実装）, Chie, Jun
> **完了**: フェーズ2の会話機能骨組みは全て完了。詳細はアーカイブ参照。

---

## フェーズ 3: LangGraph 移行 - 出力機能 `cc:TODO`

> 担当: Chie, takegg0311, テリスケ

### 3.1 VoiceAgent 移行
- [ ] Google Cloud STT 連携 `cc:TODO`
- [ ] Google Cloud TTS 連携 `cc:TODO`
- [ ] STT 補正システム移植 `cc:TODO`
- [ ] 感情タグ処理 `cc:TODO`

### 3.2 CharacterControlAgent 移行
- [ ] 感情→表情マッピング `cc:TODO`
- [ ] VRM 制御コマンド生成 `cc:TODO`

---

## フェーズ 4: 新機能 `cc:TODO`

> 担当: けいてぃー, たけがわ

### 4.1 OCRAgent 新規実装 (LangGraph のみ)
- [ ] 技術選定完了 (YOLO/Google Vision) `cc:TODO`
- [ ] 番号認識実装 `cc:TODO`
- [ ] QR コード認識 `cc:TODO`
- [ ] 表情認識実装 `cc:TODO`
- [ ] プライバシーポリシー確認 `cc:TODO`

### 4.2 EventAgent 拡張 `cc:TODO`

> フェーズ1.3で骨組み実装済み。以下は拡張機能。

- [ ] Connpass API 連携（完全実装） `cc:TODO`
- [ ] Google Calendar API 連携（完全実装） `cc:TODO`

### 4.3 GeneralKnowledgeAgent 移行 `cc:DONE` `pm:確認済`
> 完了: 2025-01-13 | 骨組み実装完了。詳細はアーカイブ参照。
- [ ] Web 検索機能 `cc:TODO` (完全実装時に実装)

---

## オープン PR 一覧

| # | タイトル | ブランチ | ステータス |
|---|----------|----------|-----------|
| 20 | RouterAgent実装 | feature/router-agent-implementation | OPEN (レビュー待ち) |

---

## 決定事項 (SSOT)

→ `.claude/memory/decisions.md` 参照

---

## メモ

- **Tailwind CSS v3.4.17 必須** - v4 は使用禁止
- **OpenAI Embeddings 1536 次元** - 768 次元は非推奨
- **モバイル AudioContext** - ユーザー操作が必要

---

## 📦 完了済みフェーズのアーカイブ

完了済みのフェーズ詳細は以下を参照:

→ [`.claude/memory/archive/Plans-archive.md`](.claude/memory/archive/Plans-archive.md)

**アーカイブ内容**:
- フェーズ 0.5: OpenRouter API徹底整備
- フェーズ 0.6: プロジェクト構造リファクタリング
- フェーズ 1.1: RouterAgent 移行
- フェーズ 1.2: BusinessInfoAgent 移行
- フェーズ 1.3: EventAgent 移行
- フェーズ 1.4: SlideAgent 移行
- フェーズ 2.1: MemoryAgent 骨組み実装
- フェーズ 2.2: ClarificationAgent 骨組み実装 (2025-01-13)
- フェーズ 2.3: LanguageClassifier 骨組み実装 (2025-01-13)
- フェーズ 4.3: GeneralKnowledgeAgent 骨組み実装 (2025-01-13)
- フェーズ 6: テスト基盤整備
- フェーズ 7.5.1-7.5.4: エージェント骨組み実装とワークフロー統合 (2025-01-13)

---

## フェーズ 7: AIロジックのバックエンド統合とフロントエンド整理 `cc:WIP`

> 担当: Claude Code
> 開始日: 2025-01-12
> ブランチ: refactor/backend-api-integration

**目的**: フロントエンド(Mastra)からバックエンド(FastAPI + LangGraph)へのAIロジック移行

**完了済み**:
- ✅ 7.1-7.4: バックエンドAPI拡張、フロントエンドプロキシ化、Mastra参照整理
- ✅ 7.6: CI/CD検証 (TypeScript 0エラー達成)

**進行中**:
- 🔄 7.5: バックエンド実装 (音声/スライド/キャラクター処理)

**7.5 バックエンド実装**

### 7.5.1-7.5.4 エージェント骨組み実装とワークフロー統合 `cc:DONE` `pm:確認済`
> 完了: 2025-01-13 | PR: #27, #28
> VoiceAgent, CharacterControlAgent, ClarificationAgent, GeneralKnowledgeAgentの骨組み実装とワークフロー統合が完了。詳細はアーカイブ参照。

**残タスク**:
- [ ] LanguageClassifier のワークフロー統合（RouterAgentから呼び出される形で既に統合済みの可能性あり、要確認）
- [ ] VoiceAgent のワークフロー統合（音声処理エンドポイント `/api/voice`）
- [ ] CharacterControlAgent のワークフロー統合（キャラクター制御エンドポイント `/api/character`）
- [ ] RouterAgent関連のファイル変更はPR#20にpush（要確認）

---

## フェーズ 8: 開発環境整備（Docker + mise + Makefile） `cc:DONE` `pm:確認待ち`

> 担当: Claude Code
> 優先度: 高（各エンジニアのローカル環境統一のため）
> 依頼日: 2025-01-13
> 完了日: 2025-01-13

**目的**: 各エンジニアが同じ開発環境で作業できるよう、Docker環境とmise/Makefileによる統一された開発コマンドを整備する

**実装完了内容**:
- ✅ mise設定ファイル（.mise.toml） - Node.js 18.20.0, Python 3.11.10, pnpm 10.12.1
- ✅ Docker環境（backend/Dockerfile, frontend/Dockerfile, docker-compose.yml, .dockerignore）
- ✅ Makefile - 統一開発コマンド（setup, dev, lint, clean等）
- ✅ ドキュメント更新（README.md, docs/development/LOCAL-DEVELOPMENT-SETUP.md）
- ✅ CI/CDチェック合格（frontend: lint/typecheck, backend: ruff/black）

### 8.1 mise設定（バージョン管理基盤） `cc:TODO`

**目的**: Node.js, Python, pnpmなどのバージョンを統一管理

**タスク**:
- [ ] `.mise.toml` 作成
  - [ ] Node.js バージョン指定（>=18.0.0）
  - [ ] Python バージョン指定（>=3.11.0）
  - [ ] pnpm バージョン指定（>=8.0.0）
  - [ ] その他必要なツール（Supabase CLI等）の指定
- [ ] `.mise.toml` の動作確認
  - [ ] `mise install` で全ツールがインストールされることを確認
  - [ ] バージョンが正しく設定されることを確認

**影響ファイル**:
- `.mise.toml` (新規作成)

**受け入れ基準**:
- ✅ `mise install` で全ツールがインストールされる
- ✅ `mise exec -- <command>` で正しいバージョンのツールが実行される
- ✅ README.mdにmiseセットアップ手順を追加

---

### 8.2 Docker環境構築 `cc:TODO`

**目的**: フロントエンド・バックエンドをDockerコンテナで統一実行

**タスク**:
- [ ] `backend/Dockerfile` 作成
  - [ ] Python 3.11 ベースイメージ
  - [ ] requirements.txt からの依存関係インストール
  - [ ] 開発用設定（ホットリロード対応）
  - [ ] 本番用設定（マルチステージビルド）
- [ ] `frontend/Dockerfile` 作成
  - [ ] Node.js 18+ ベースイメージ
  - [ ] pnpm インストール
  - [ ] 依存関係インストール
  - [ ] 開発用設定（Next.js dev server）
  - [ ] 本番用設定（Next.js build + start）
- [ ] `docker-compose.yml` 作成（ルート）
  - [ ] frontend サービス定義
  - [ ] backend サービス定義
  - [ ] 環境変数設定（.env ファイル連携）
  - [ ] ボリュームマウント（ホットリロード用）
  - [ ] ネットワーク設定
  - [ ] ポートマッピング（3000, 8000）
- [ ] `.dockerignore` 作成（frontend, backend）
  - [ ] node_modules, __pycache__ 等の除外設定
- [ ] Docker環境の動作確認
  - [ ] `docker-compose up` でフロントエンド・バックエンドが起動
  - [ ] ホットリロードが動作することを確認
  - [ ] 環境変数が正しく読み込まれることを確認

**影響ファイル**:
- `backend/Dockerfile` (新規作成)
- `frontend/Dockerfile` (新規作成)
- `docker-compose.yml` (新規作成)
- `backend/.dockerignore` (新規作成)
- `frontend/.dockerignore` (新規作成)

**受け入れ基準**:
- ✅ `docker-compose up` でフロントエンド（localhost:3000）とバックエンド（localhost:8000）が起動
- ✅ コード変更がホットリロードで反映される
- ✅ 環境変数が正しく読み込まれる
- ✅ CI/CDでDockerビルドが成功する

---

### 8.3 Makefile作成（統一コマンド） `cc:TODO`

**目的**: miseとDockerを使った統一された開発コマンドを提供

**タスク**:
- [ ] `Makefile` 作成（ルート）
  - [ ] `make setup` - 初回セットアップ（mise install + Docker build）
  - [ ] `make install` - 依存関係インストール（mise経由）
  - [ ] `make dev` - 開発サーバー起動（docker-compose up）
  - [ ] `make dev:frontend` - フロントエンドのみ起動
  - [ ] `make dev:backend` - バックエンドのみ起動
  - [ ] `make build` - ビルド（フロントエンド + バックエンド）
  - [ ] `make test` - テスト実行
  - [ ] `make lint` - リンター実行
  - [ ] `make clean` - クリーンアップ（コンテナ停止、ボリューム削除）
  - [ ] `make help` - ヘルプ表示
- [ ] Makefileの動作確認
  - [ ] 各コマンドが正しく動作することを確認
  - [ ] miseとDockerが適切に連携することを確認

**影響ファイル**:
- `Makefile` (新規作成)

**受け入れ基準**:
- ✅ `make setup` で初回セットアップが完了
- ✅ `make dev` で開発環境が起動
- ✅ `make help` で全コマンドが表示される
- ✅ README.mdにMakefileの使い方を追加

---

### 8.4 ドキュメント更新 `cc:TODO`

**タスク**:
- [ ] `README.md` 更新
  - [ ] miseセットアップ手順追加
  - [ ] Dockerセットアップ手順追加
  - [ ] Makefileコマンド一覧追加
  - [ ] クイックスタートガイド更新
- [ ] `docs/development/LOCAL-DEVELOPMENT-SETUP.md` 更新
  - [ ] Docker環境のセットアップ手順追加
  - [ ] miseの使い方追加
  - [ ] Makefileの使い方追加
- [ ] `.gitignore` 確認・更新
  - [ ] Docker関連ファイルの除外確認
  - [ ] mise関連ファイルの除外確認

**影響ファイル**:
- `README.md` (更新)
- `docs/development/LOCAL-DEVELOPMENT-SETUP.md` (更新)
- `.gitignore` (確認・更新)

**受け入れ基準**:
- ✅ 新規エンジニアがREADME.mdを読んで環境構築できる
- ✅ Docker/mise/Makefileの使い方が明確に記載されている

---

**実装順序（推奨）**:
1. **8.1 mise設定** → バージョン管理の基盤を整備
2. **8.2 Docker環境構築** → 開発環境の統一
3. **8.3 Makefile作成** → 統一コマンドの提供
4. **8.4 ドキュメント更新** → 使い方の明文化

**リスク / 注意点**:
- Docker環境は既存のローカル環境と競合する可能性がある（ポート3000, 8000）
- miseは既存のNode.js/Python環境と競合しないよう、PATH設定に注意
- Makefileは各OS（macOS, Linux, Windows）で動作するよう配慮（WindowsはWSL2推奨）

**次のアクション候補**:
1. フェーズ8.1から開始（mise設定）
2. 既存エンジニアへのヒアリング（Docker環境の要望確認）

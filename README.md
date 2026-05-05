# Engineer Cafe Navigator

> 福岡・エンジニアカフェ向けの **キオスク／多言語ボイス対応のプロダクション AI エージェント**。単一 LLM にセリフを丸投げする「AI チューバー型」のスタックではなく、**バックエンドに集約したマルチエージェント・RAG・評価ゲート**まで含んだ構成です。

**[English](README-EN.md)** | **日本語**

## 現在地（要約）

運用上の**正本**は **[docs/STATUS.md](docs/STATUS.md)** です（**2026-05-05** に git 同期メモと読み方を追記済み。live workflow を再実行するまで NO-GO 記録の日付は 05-03 のまま参照されます）。スナップショット・Issue・品質ゲートの判断は、`README` ではなく常にそちらを優先してください。

**ドキュメントの地図**: **[docs/README.md](docs/README.md)**  
ツール向けの CI・コマンド・レイヤ制約: **[CLAUDE.md](CLAUDE.md)**

---

## 一般的な AI アバター／単一エージェント実装との違い

| 観点 | よくあるスタック | Engineer Cafe Navigator |
|------|------------------|-------------------------|
| 知性の置き場所 | フロントまたは単一エンドポイントにロジックが分散しがち | **[バックエンドファースト](docs/adr/005-backend-first-logic.md)** — ルーティング・RAG・受付・音声の正本は FastAPI + LangGraph（[ADR 一覧](docs/adr/README.md)） |
| フロントとの関係 | アプリとモデル呼び出しが一体化しやすい | Next.js は **UI と `/api/*` プロキシ**。バックエンドは **HTTP 契約**で別クライアント（Unity 等）とも統合しやすい（ADR 005） |
| エージェント構造 | 1 システムプロンプトで全部処理 | **LangGraph + Supervisor**。**受付はサブグラフ**（[ADR 006](docs/adr/006-langgraph-workflow-redesign.md)、`invoke_reception_subgraph`） |
| ナレッジ検索 | 単純ベクトル検索のみ | **Enhanced RAG** — 階層検索・親コンテキスト（`backend/tools/enhanced_rag.py`）。多言語 **tRAG** |
| 記憶 | セッション内のみ | **短期**: Checkpointer / `agent_memory`。**長期**: [ADR 011](docs/adr/011-ltm-cross-session-design.md) / [012](docs/adr/012-ltm-connection-pool-migration.md)（コード・STATUS と突合） |
| 品質 | 手動デモ中心 | **RAGAS**、`backend/evaluation/`、[ADR 019](docs/adr/019-alpha-live-ragas-case-accounting.md)、[STATUS](docs/STATUS.md) |
| キオスク UX | 緩い | **[ADR 018](docs/adr/018-alpha-fast-response-and-assistant-profile-routing.md)** — identity/help の経路契約 |

設計議論: [docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md](docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md)

---

## アーキテクチャ（概要）

```text
Browser / Kiosk
  -> Next.js 15（UI / VRM / /api/* プロキシ）
  -> FastAPI（LangGraph・Enhanced RAG・受付・音声・カレンダー・キャラ制御）
  -> Supabase（pgvector・会話状態・ナレッジ）/ OpenRouter / 外部フィード
```

- `frontend/` … [frontend/README.md](frontend/README.md)
- `backend/` … [backend/README.md](backend/README.md)
- `docs/` … STATUS・ADR・手順

---

## クイックスタート

### 前提

Node.js 20 / pnpm 10 / Python 3.11+（細目は CLAUDE.md）。Docker は `make dev` で利用可能。

### フロントエンド

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

### バックエンド

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### モノレポ（Docker）

```bash
make dev
```

---

## ドキュメントを読む順番（推奨）

| 順 | 内容 |
| --- | --- |
| 1 | [docs/STATUS.md](docs/STATUS.md) |
| 2 | [docs/README.md](docs/README.md) |
| 3 | [docs/architecture/SYSTEM-ARCHITECTURE.md](docs/architecture/SYSTEM-ARCHITECTURE.md) |
| 4 | [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md) |
| 5 | [CLAUDE.md](CLAUDE.md) |
| 6 | [frontend/README.md](frontend/README.md) / [backend/README.md](backend/README.md) |

計画のみ: [docs/plans/comprehensive-refactoring-plan-2026-05-05.md](docs/plans/comprehensive-refactoring-plan-2026-05-05.md)

---

古い Mastra 前提の長文は [docs/archive/](docs/archive/) にあります。現行は **STATUS.md** とコードを優先してください。


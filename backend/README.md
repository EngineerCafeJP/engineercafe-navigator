> **Docs hub**: [docs/README.md](../docs/README.md) · **STATUS**: [docs/STATUS.md](../docs/STATUS.md)

# バックエンド

FastAPI + LangGraph。**会話・音声・スライド・キャラ・ナレッジ・受付のランタイム正本**。フロントは UI／プロキシ層です。

## 役割

- `backend/main.py` … FastAPI と主要エンドポイント
- `backend/workflows/` … LangGraph
- `backend/agents/` … ドメイン／サポートエージェント
- `backend/api/` … ナレッジ・受付・STT 語彙など
- `backend/services/` … 受付ハンドオフ・座席・来館者・翻訳など
- `backend/tests/` … 自動検証

## エンドポイント早見

`GET /health`、`GET /api/calendar`、`POST /api/chat`、`POST /api/chat/stream`、`POST /api/agent/invoke`、`POST /api/voice`、`POST /api/slides`、`POST /api/character`、`POST /api/ocr`、`POST /api/interrupt`、`/api/knowledge/*`、`/api/stt-vocabulary/*`、`/api/reception/*`。**詳細は OpenAPI `/docs`**。

## 実装上のメモ

- `API_SECRET_KEY` なしのローカルは緩いが、`staging` / `production` は fail-closed。
- レート制限は `slowapi` 依存。
- 受付セッションは `ReceptionRepository` → Supabase。受付ワークフローはシングルトン + `asyncio.Lock`。
- 受付サブグラフ `invoke_reception_subgraph()`（PR #390 統合）。`consultation` → `general_knowledge`。
- 多言語 RAG は tRAG（英→日本語寄せ等）。ナレッジ本文は日本語中心。

## 環境変数

`backend/.env.example`、`.env.staging.example`、`.env.production.example` を参照。[docs/STATUS.md](../docs/STATUS.md) とコードを優先。

## 動線

[docs/README.md](../docs/README.md) → [STATUS](../docs/STATUS.md) → [SYSTEM-ARCHITECTURE](../docs/architecture/SYSTEM-ARCHITECTURE.md) → [setup-guide](../docs/setup-guide.md)

## ローカル

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## テスト

```bash
pytest -m "not ragas and not slow and not e2e" --tb=short -q
pytest tests/api -q
```

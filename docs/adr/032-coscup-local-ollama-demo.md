# ADR-032: COSCUP 2026 ライブデモ向け ローカル完結 LLM / RAG / TTS 構成

## Status

Accepted (2026-08-05) — COSCUP 2026（台北, 2026-08-08）ライブデモ専用。本番（エンジニアカフェ実運用）の設定・挙動は不変。すべての変更は env-gated / profile 分離。

## Context

登壇者は「公共施設は来場者の音声を外部サーバーに送るべきではない」という主張を、**MacBook + Docker のローカル完結デモ**で実証する。デモは 2 項目のみ:

1. 英語音声 → 英語音声の 1 往復（例: "What can I do at Engineer Cafe?"）
2. 回答再生中の割り込み → ポライトな停止（ボタン型バージイン）

制約: デモ本体は**完全オフライン**で動作（例外: Google Calendar API のみ、不使用なら発動しない）。デモ中の外向き通信はゼロでなければ「entirely local」の主張が崩れる。

実態調査（2026-08-05）の結果、音声パイプラインは以下で構成されていた:

| 段 | 実装 | 接続 | オフライン可否 |
|---|---|---|---|
| STT | Qwen3-ASR 0.6B (CPU/ONNX) プライマリ + Vosk フォールバック | ローカル | ✅ |
| LLM | `get_llm_provider()` シングルトン → **OpenRouter**（クラウド） | **クラウド** | ❌ |
| Embedding | OpenRouter `/v1/embeddings` | **クラウド** | ❌ |
| RAG 検索 | Supabase RPC `search_knowledge_base` | **クラウド** | ❌（テキスト/YAML ローカルフォールバックは既存） |
| TTS | PiperPlus プライマリ（ローカル）→ Kokoro 英語フォールバック | ローカル | ✅（但し piper-plus の Docker artifact はリポジトリ外） |
| 割り込み | `/api/voice` action=interrupt → `SessionTaskManager.cancel_all_tasks` + フロント側音声即停止 | — | ✅ |

遮断点は LLM 生成・Embedding 生成・RAG ベクトル検索の 3 点のみ。また `orchestrator_agent` / `general_knowledge_agent` / `ocr_agent` / `language_processor` / `purpose_classifier` が **OpenRouterProvider を直接インスタンス化**しており（factory 経由でない）、デモ時に env を切り替えてもクラウド通信が残る潜在リークだった。

## Decision

### D1: LLM プロバイダ抽象化（env-gated）

- `backend/llm/ollama.py` に `OllamaProvider(LLMProvider)` を新設。OpenAI 互換 `/v1/chat/completions` を httpx で呼び、`LLMResponseText`（provider/model/llm_latency_ms メタデータ）を返す。
- `backend/llm/provider.py` の `get_llm_provider()` は `LLM_PROVIDER=ollama` のとき OllamaProvider を選択（既定は従来どおり OpenRouterProvider）。
- **`resolve_llm_provider(api_key=None)` ヘルパーを新設**し、直接インスタンス化していた 5 箇所（orchestrator / general_knowledge / ocr / language_processor / purpose_classifier）を経由させる。`LLM_PROVIDER=ollama` 時は共有シングルトンとは別の OllamaProvider を返す（close() によるシングルトン破壊を回避）。
- Ollama ペイロードは `reasoning_effort: "none"`（Qwen3 系 thinking 無効化。ベンチマークで TTFT 37s → 0.4s に改善）と `keep_alive: 30m`（ターン間アンロード防止）を含む。

### D2: Embedding / RAG のローカル化（env-gated）

- `embedding_service.py`: `EMBEDDING_API_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` / `EMBEDDING_API_KEY` で上書き可能に（既定は従来の OpenRouter 値）。
- `RAG_VECTOR_BACKEND=local-pgvector` で、compose 内 postgres（pgvector）へ psycopg 非同期接続し `search_knowledge_base_local` SQL 関数でコサイン検索。行契約は既存 YAML フォールバックと同一。エラー時は既存のテキスト/YAML フォールバックへ自動落下。
- `backend/scripts/seed_local_knowledge.py` が `backend/knowledge/data/*.yaml`（ja+en）を Ollama embedding でローカル DB にシード。

### D3: デモ設定の分離（本番不変）

- `docker-compose.demo.yml`（override）: デモ env 一式 + `--profile voice` の kokoro-tts。observability 系は起動しない（明示サービスリスト + `depends_on: !override`）。
- フロントエンド: `NEXT_PUBLIC_DEMO_MODE=true` で初期言語 en + 初回モーダルの英語プリセレクト、TTS provider 'kokoro' を送信。
- 言語強制 `LANGUAGE_FORCE=en`、簡潔回答 `DEMO_CONCISE_ANSWER=true`（en 指示に 2-3 文制約を追記）、カレンダー失敗時の自然な英語フォールバック文言。
- オフライン硬直化: `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` / `NUMBA_CACHE_DIR=/app/.numba_cache`（librosa/numba JIT キャッシュ問題の回避。これが無いと Qwen ONNX が RuntimeError で落ちる）。
- TTS は Kokoro プライマリ（piper-plus サーバーが本リポジトリに不在のため）。`TTS_PROVIDER=kokoro` を `voice_agent` / `api/voice` の許可リストへ追加（env 既定は piper のまま）。

### D4: 推奨 LLM モデル

ベンチマーク（`scripts/demo/benchmark_ollama.py`、RAG 文脈込み・ウォーム・thinking off）:

| モデル | TTFT | 完答 | 判定 |
|---|---|---|---|
| **qwen3.6:35b** | **~0.4s** | **~1.0s** | **採用（品質最良・最速）** |
| qwen3.5:9b | ~0.5s | ~1.4s | 控え（同系統） |
| gemma4:e4b | ~0.5-0.8s | ~2-3s | 控え |
| gemma4:e2b | ~0.3-0.9s | ~1-1.7s | 控え（小メモリ） |
| qwen3:8b | ~0.6s | ~2-3s | 控え |

※ thinking 有効時は全 Qwen 系が 37s+ でデモ不能（`reasoning_effort: none` 必須）。メモリ約 23GB（qwen3.6:35b）。

## Consequences

### 良いこと

- デモ中の外向き通信ゼロを実現（LLM/Embedding/RAG がローカル）。tcpdump + Wi-Fi 切断で証跡化（`scripts/demo/offline-proof.sh`）。
- 本番設定に一切触れない（全 env 既定値は従来動作）。
- 実測 E2E（ウォーム、2026-08-05）: STT ~0.4s + LLM ~3.8s + TTS ~2-4s ≈ **7-9s**。割り込みは API レベルで 10/10 成功。ノイズ SNR 5dB でもデモ質問 2 文を正認識。

### リスク・注意

- qwen3.6:35b は ~23GB のメモリを要する。MacBook の空き RAM が不足する場合は gemma4:e2b へ切替（`OLLAMA_MODEL` のみ変更）。
- モデルのダウンロード（Ollama pull / Qwen ONNX / Vosk / 翻訳モデル）は**準備時**に必要（デモ実行時は不要）。Wi-Fi 切断前に済ませること。
- ローカル RAG はシード済み `knowledge_embeddings` テーブルが前提。シードは `scripts/demo/warmup.sh` の前に `backend/scripts/seed_local_knowledge.py` を 1 回実行（ドキュメント参照）。
- `/api/voice` は 20/min のレート制限あり（本番セキュリティ）。デモは 3 往復以内なので影響なし。
- STT 初回推論は numba コンパイル等で数秒かかる（warmup.sh が吸収）。

### 検証（2026-08-05）

- backend テスト: 3878 passed / 0 failed（43 skip は TTS エンジン不在等の環境依存・従来と同数）。
- frontend: 161 passed / tsc クリーン。
- デモ E2E 実測・割り込み 10/10・ノイズ耐性・オフライン証跡: `docs/demo/coscup2026/REPORT.md` 参照。

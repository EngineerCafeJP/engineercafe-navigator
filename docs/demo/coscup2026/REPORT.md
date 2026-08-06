# COSCUP 2026 ライブデモ 実装レポート

日付: 2026-08-05 / 追補: 2026-08-06（PiperPlus パリティ回復） ｜ ブランチ: `feat/coscup2026-local-demo` ｜ ベース: `develop`

## 1. 現行パイプライン構成（調査結果・コードと compose から確定）

| 段 | 実装 | モデル / 接続 | オンライン依存 |
|---|---|---|---|
| STT | Qwen3-ASR 0.6B ONNX（CPU）プライマリ + Vosk(en/ja) フォールバック | ローカル（`/app/models/qwen3-asr-0.6b-onnx`） | なし（DL は準備時のみ） |
| LLM | `get_llm_provider()` シングルトン | **変更前: OpenRouter（クラウド）→ 変更後: Ollama `qwen3.6:35b`（Metal GPU）** | 変更前: あり ❌ → 変更後: なし ✅ |
| Embedding | `embedding_service.py` | 変更前: OpenRouter → 変更後: Ollama `nomic-embed-text`（768d） | 変更前: あり → 変更後: なし |
| RAG 検索 | `EnhancedRAGSearch` | 変更前: Supabase RPC → 変更後: ローカル postgres(pgvector) `search_knowledge_base_local`（シード 78 行） | 変更前: あり → 変更後: なし |
| TTS | PiperPlus（tsukuyomi-chan-6lang・en=対応）プライマリ + Kokoro(af_bella) フォールバック | ローカル `piper-plus:8090`（Docker・モデルビルド時同梱）+ `kokoro-tts:8880` | なし（DL はビルド時のみ） |
| 割り込み | `/api/voice` action=interrupt → `SessionTaskManager.cancel_all_tasks` + フロント `AudioQueue.clear` + `WebAudioPlayer.stop` | — | なし |
| 言語 | ヒューリスティック検出（ja/en/zh/ko）+ `LANGUAGE_FORCE=en` 強制 | — | なし（LLM フォールバック検出も Ollama 化） |
| Calendar | `GOOGLE_CALENDAR_ICAL_URL` 未設定 → 非発動。デモ時は自然な英語フォールバック文言 | — | 例外（デモでは不使用） |
| その他 | Discord / LangSmith / Tavily / Connpass / Supabase memory は全て env-gated（未設定で劣化動作） | — | なし |

### 発見されたクラウドリーク（修正済み）

`orchestrator_agent` / `general_knowledge_agent` / `ocr_agent` / `language_processor` / `purpose_classifier` が **OpenRouterProvider を直接インスタンス化**していた。`LLM_PROVIDER=ollama` でもクラウド通信が残る潜在リーク → `resolve_llm_provider()` ヘルパー（provider.py）経由に統一。

### その他のトラブルシューティング（実証中に発見・修正）

1. **librosa/numba の `cannot cache function '__o_fold'`** — dev イメージに `NUMBA_CACHE_DIR` 未設定が原因。`NUMBA_CACHE_DIR=/app/.numba_cache` で解決（Qwen ONNX が 7.6s → 0.4s）。
2. **KOKORO_API_URL の `/v1` 重複** — クライアントが `/v1/audio/speech` を付加するため base に `/v1` を含めない。
3. **Kokoro fallback タイムアウト（3s）** — CPU 合成は 2-3 文で 3-5s かかるため `TTS_KOKORO_TIMEOUT_SECONDS=30` に延長。
4. **デモ用 API 認証** — ローカル `.env` の `API_SECRET_KEY` が認証を要求 → デモ override で `API_SECRET_KEY: ""`（認証無効化）。
5. **piper-plus 不在** — 本リポジトリに Docker artifact なし（`docker/piper-plus` は参照のみ）→ デモは Kokoro プライマリに切替。
6. **Qwen3 thinking モード** — 有効時 TTFT 37s+ でデモ不能。`reasoning_effort: "none"` で 0.4s に改善。

## 2. LLM モデルベンチマーク結果

方法: `scripts/demo/benchmark_ollama.py` — RAG 文脈（`backend/knowledge/data/*.yaml` の content_en）込み・ウォーム・ストリーミングで TTFT/完答を計測。`reasoning_effort=none` 適用後:

| モデル | load_ms | q1 TTFT/完答 | q2 TTFT/完答 | q3 TTFT/完答 | 判定 |
|---|---|---|---|---|---|
| **qwen3.6:35b** | 318 | **435/1308** | **388/859** | **477/864** | **推奨（品質最良）** |
| qwen3.5:9b | 331 | 511/1443 | 470/2399 | 2302/5137 | 控え |
| gemma4:e4b | 3524 | 458/3283 | 828/1936 | 571/2035 | 控え |
| gemma4:e2b | 3175 | 341/973 | 368/1407 | 912/1682 | 控え（小メモリ） |
| qwen3:8b | 2237 | 622/3326 | 656/2199 | 575/1568 | 控え |

※ thinking 有効時の計測（benchmark2）: qwen3.6:35b は 37,326ms でデモ不可。
※ メモリ: qwen3.6:35b ≈ 23GB。RAM 不足時は gemma4:e2b。

回答品質（qwen3.6:35b・抜粋）:
- "You can cowork in the Main Hall with free seats and Wi-Fi, or explore latest tech like the Apple Vision Pro and Tello drone. The B1F MAKER's Space offers fabrication tools..." ✅
- "The restrooms are located at the far end of the 1F terrace, not directly inside the building. To reach them, please go through the passage behind the reception desk..." ✅

証跡: `evidence/benchmark3/*.json` / `summary.json`

## 3. 区間別レイテンシ（最適化前後）

デモ① "What can I do at Engineer Cafe?"（WAV: `scripts/demo/audio/q1_what_can_i_do.wav`、1.99s 音声）

| 区間 | 最適化前 | 最適化後 | 主な変更 |
|---|---|---|---|
| STT（音声終了→transcript） | ~2.8s（Vosk レース勝ち） | **0.4s**（Qwen ONNX、NUMBA_CACHE_DIR 修正 + hedge=0） | numba キャッシュ / レース無効化 |
| LLM（transcript→answer） | 16.4s（空 query + コールド） | **~3.8s**（warm: orchestrator + agent の 2 コール） | reasoning_effort=none / keep_alive 1h / 簡潔指示 |
| TTS（answer→audio） | 6.2s（piper 失敗待ち + kokoro 3s timeout） | **0.04-0.2s**（PiperPlus プライマリ。8/6 パリティ回復後） | docker/piper-plus + TTS_PROVIDER=piper |
| **E2E 合計** | ~12.8s | **~2-9s**（Q2 fast path 0.9s / Q3 2.1s / Q1 3.9-8s warm） | — |

### 3b. デモ Q1〜Q3 の TTS レイテンシ（8/6 PiperPlus 構成・実測）

| 質問 | 回答文長 | PiperPlus TTS | Kokoro 時（参考） | E2E（piper 構成） |
|---|---|---|---|---|
| Q1 What can I do at Engineer Cafe? | ~180字 | **147ms** | ~3.7s | 3.9-8s（LLM 2コール。コールド時 20s → warmup で回避） |
| Q2 Where is the toilet?（fast path） | ~160字 | **137ms** | ~3.0s | **0.9s** |
| Q3 Is the cafe open on weekends? | ~150字 | **171ms** | ~2.5s | **2.1s** |

PiperPlus は Kokoro 比 **約 15-20 倍高速**（合成 36-41ms + 転送）。回答音声は 22050Hz WAV（Kokoro と同形式・LipSync 互換）。

### 3c. PiperPlus パリティ回復（8/6 追補）

- `docker/piper-plus/` 新設: piper-plus 1.13.0（pip）の `PiperVoice` をラップする FastAPI アダプタ。`POST /synthesize`（backend `PiperPlusTTSClient` 互換）→ WAV。`GET /api/voices`（healthcheck）。
- モデル: **tsukuyomi-chan-6lang-fp16.onnx（39MB・MB-iSTFT・ja/en/zh/es/fr/pt）** — production ドキュメントが参照するモデルそのもの。en は MultilingualPhonemizer が文単位自動判定。
- ビルド時に同梱: モデル + nltk データ（g2p-en 用: averaged_perceptron_tagger_eng / cmudict。旧名 zip も配置）。**実行時のネットワーク取得ゼロ**。
- ARM64（Apple Silicon）動作確認済み（onnxruntime / pyopenjtalk-plus の aarch64 wheel）。
- タイムアウト等: `TTS_PIPER_TIMEOUT_SECONDS=20` / `TTS_PIPER_PRIMARY_TIMEOUT_SECONDS=20` / `PIPER_PLUS_MAX_ATTEMPTS=2` / `PIPER_PLUS_RETRY_BACKOFF_SECONDS=0.15`（compose 明示）。
- フロント: `getTtsProvider()` は既定 `piper`（`NEXT_PUBLIC_TTS_PROVIDER` で override 可能）。
- 割り込み: piper 再生中（合成中）の backend キャンセル 10/10。回答再生中の停止はフロント `WebAudioPlayer.stop()`（即時・プロバイダ非依存）。※ 同一テキストの TTS キャッシュヒット時は合成タスクが存在しないため `no_active_task` が正常応答（キャッシュから即返るだけ）。
- **ビルド所要**: ネットワークが遅い環境で約 37 分（pip + モデル取得）。デモ前の準備フェーズで 1 回だけ実行: `docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice build piper-plus`

## 4. 割り込みデモ（10 回連続検証）

方法: 長文 TTS 開始後に `action=interrupt` → `interruptStatus=cancelled` → 別セッションで新 TTS 成功、を 10 回繰り返し。

結果:
- **Kokoro 構成（8/5）: 10/10 成功**（interrupt 0.6s 後）
- **PiperPlus 構成（8/6）: 10/10 成功**（interrupt 0.02-0.4s 後、テキスト毎回ユニークで合成中にキャンセル。※ TTS キャッシュヒット時は合成タスクが無いため `no_active_task` が正常）

エコー誤爆: デモはボタン型バージイン（回答再生中マイク OFF）のため、スピーカー出力の回り込みによる誤爆は構造的に発生しない。回答再生の停止はフロント側（`AudioQueue.clear()` + `WebAudioPlayer.stop()`）で即時に行われ、backend 割り込みは合成タスクの安全停止を担う。

## 5. 会場ノイズ耐性

方法: デモ質問 2 文の WAV にピンクノイズを SNR 10dB / 5dB で重畳 → STT。

| 入力 | SNR 10dB | SNR 5dB |
|---|---|---|
| "What can I do at Engineer Cafe?" | 正認識（424ms） | **正認識（440ms）** |
| "Where is the toilet?" | 正認識（514ms） | **正認識（426ms）** |

※ 実機でのヘッドセット想定（口元マイク）は SNR 5dB より良好。証跡: `evidence/noise/q1_snr5.wav` 等。

## 6. オフライン実証

`bash scripts/demo/offline-proof.sh`（Wi-Fi 切断 → tcpdump → デモ 2 項目 + 割り込み完走 → pcap 解析 → Wi-Fi 復元）。

- **8/5（Kokoro 構成）**: 完走・**tcpdump 0 パケット**。証跡: `evidence/offline/`
- **8/6（PiperPlus 構成）**: 完走・0 パケット。証跡: `evidence/offline2/`（PiperPlus プライマリでの再実行）

⚠️ 注意: デモ①の LLM コールドリロード（~20s）は **keep_alive=1h が切れた後**に発生。デモ当日は warmup.sh を直前に実行し、30 分以上間を空けないこと。

## 7. テスト

- backend: `pytest -m "not ragas and not slow and not e2e"` → **3881 passed / 0 failed**（41 skip は Supabaseローカル 35 / VoiceVox不在 4 / --run-llm 2。8/5 と同数・piper 導入による増減なし — piper ゲートの探索は e2e マーク側にあるため）
- frontend: **163 passed / 0 failed** / `tsc --noEmit` クリーン
- 新規テスト: Ollama provider（23）・resolve_llm_provider（4）・local RAG（18）・embedding env（11）・言語強制/簡潔指示/カレンダー文言（24）・デモモード（7）

## 8. 成果物一覧

| 成果物 | 場所 |
|---|---|
| デモ起動手順書（1ページ） | `docs/demo/coscup2026/README.md` |
| 障害時フォールバック手順 | `docs/demo/coscup2026/FALLBACK.md` |
| ADR | `docs/adr/032-coscup-local-ollama-demo.md` |
| ベンチ結果 | `docs/demo/coscup2026/evidence/benchmark3/` |
| ノイズ証跡 | `docs/demo/coscup2026/evidence/noise/` |
| オフライン証跡 | `docs/demo/coscup2026/evidence/offline/`（実行後） |
| スクリプト | `scripts/demo/{up,down,warmup,health,latency,offline-proof}.sh`・`benchmark_ollama.py` |
| compose | `docker-compose.demo.yml` |

# COSCUP 2026 ライブデモ 起動手順書（1ページ）

登壇用 MacBook（Apple Silicon・Docker Desktop）での完全ローカルデモ手順。
デモは 2 項目: **①英語 Q&A 1往復** → **②回答中の割り込み→ポライト停止**。
所要時間の目安は各ステップ末尾の `⏱`。

## 0. 事前準備（渡航前に 1 回だけ・Wi-Fi 必要）

```bash
# モデル類（デモ実行時はネット不要。必ず事前に）
ollama pull qwen3.6:35b && ollama pull nomic-embed-text
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice \
  run --rm backend bash scripts/download_qwen_onnx_model.sh /app/models/qwen3-asr-0.6b-onnx
```
⏱ 20〜40 分（回線次第）

## 1. 起動（会場到着後）

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice \
  up -d frontend backend postgres kokoro-tts   # または:
bash scripts/demo/up.sh
```
⏱ 初回 3 分 / 2 回目以降 1 分（モデル DL 済みなら）

## 2. RAG シード（初回のみ）

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice \
  exec backend python scripts/seed_local_knowledge.py
```
⏱ 30 秒（"Seed complete: N rows" を確認）

## 3. ウォームアップ（全モデルをメモリへ・デモ直前）

```bash
bash scripts/demo/warmup.sh
```
⏱ 30 秒〜1 分（STT モデルロード + LLM 1往復 + 回答 2 件の TTS キャッシュ生成）

⚠️ **ウォームアップ後 30 分以内にデモを開始すること**（LLM は keep_alive=1h で保持されるが、空けすぎるとコールドリロードで 20s かかる。デモ直前の実行を推奨）。

## 4. ヘルスチェック

```bash
bash scripts/demo/health.sh      # backend /health + frontend 200
curl -s http://localhost:8000/health   # {"status":"ok",...}
ollama ps                        # qwen3.6:35b が LOADED であること
```
⏱ 10 秒

## 5. 画面切替（デモ開始）

1. ブラウザで `http://localhost:3000` を開く（デモモード: 英語初期化・en プリセレクト済み）
2. 初回モーダルで「English」→ Start
3. マイク許可を「Allow」
4. ミュート解除・スピーカー音量確認（ヘッドセット推奨）

**デモ①**: マイクボタン長押し → 「What can I do at Engineer Cafe?」→ 放して回答待ち
**デモ②**: 回答再生中にマイクボタンを押す → 即停止 → 「Where is the toilet?」で新質問
⏱ 各ターン 8〜10 秒（フィラー音声が待ち時間を埋める）

## 6. 終了

```bash
bash scripts/demo/down.sh
```

## 障害時クイックチェック

| 症状 | 確認 | 対処 |
|---|---|---|
| 回答が日本語になる | LANGUAGE_FORCE 確認 | compose 再作成: `up -d backend` |
| STT が返らない | `docker compose ... logs backend` | warmup.sh 再実行（モデルロード） |
| TTS が無音/失敗 | kokoro-tts の health | `docker compose ... up -d kokoro-tts` |
| LLM が遅い/停止 | `ollama ps`（モデル unload してないか） | warmup.sh 再実行 |
| RAM 不足 | Activity Monitor | `OLLAMA_MODEL=gemma4:e2b` に変更 → `up -d backend` |

→ 全滅時のフォールバックは [`FALLBACK.md`](./FALLBACK.md) へ。

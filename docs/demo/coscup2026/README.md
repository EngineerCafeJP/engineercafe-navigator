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
# PiperPlus TTS イメージ（モデル同梱・約37分。ネットワーク遅い環境は長めに）
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice build piper-plus
```
⏱ 40〜80 分（回線次第。PiperPlus ビルドは一度だけ）

## 1. 起動（会場到着後）

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice \
  up -d frontend backend postgres piper-plus kokoro-tts   # または:
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

⚠️ **デモ中は `bash scripts/demo/heartbeat.sh` をバックグラウンドで実行すること**
（backend は Ollama の OpenAI 互換 API を使うため、リクエスト側の `keep_alive`
は無視される＝実測済み。モデルは Ollama サーバー既定 keep_alive（通常 5 分）で
アンロードされ、次のターンはコールドリロード ~12.5s かかる＝実機で
「2 問目がタイムオーバー」の原因になった。heartbeat は native `/api/chat` に
`keep_alive=1h` を送り、モデルを常駐させる）。

```bash
nohup bash scripts/demo/heartbeat.sh >/dev/null 2>&1 &   # デモ中はこのまま
```
`ollama ps` で `UNTIL 59 minutes from now` が出ていれば保持されている。

## 4. ヘルスチェック

```bash
bash scripts/demo/health.sh      # backend /health + frontend 200
curl -s http://localhost:8000/health   # {"status":"ok",...}
ollama ps                        # qwen3.6:35b が LOADED（UNTIL が近い/切れていたら heartbeat 再開）
```
⏱ 10 秒

## 5. 画面切替（デモ開始）

1. ブラウザで `http://localhost:3000` を開く（デモモード: 英語初期化・en プリセレクト済み）
2. 初回モーダルで「English」→ Start
3. マイク許可を「Allow」
4. ミュート解除・スピーカー音量確認（ヘッドセット推奨）
5. 画面右上の ⚙ 設定 → **Multimedia タブ →「音声スピード」** で話速を調整
   （1.0=標準。実機検証の指摘を受けデフォルト構成は 0.65 ≒ ゆっくり。
   スライダー 0.50〜1.50 の範囲でリアルタイム調整可能・次回起動時も保持）

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
| TTS が無音/失敗 | piper-plus と kokoro-tts の health | `docker compose ... up -d piper-plus kokoro-tts` |
| LLM が遅い/停止 | `ollama ps`（モデル unload してないか） | heartbeat 再開 or warmup.sh 再実行 |
| RAM 不足 | Activity Monitor | `OLLAMA_MODEL=gemma4:e2b` に変更 → `up -d backend` |

TTS フォールバック順: **① PiperPlus（tsukuyomi-chan-6lang）→ ② Kokoro（ローカル）→ ③ ホステッド版 → ④ 録画60秒**（詳細は [`FALLBACK.md`](./FALLBACK.md) へ）。

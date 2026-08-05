# COSCUP 2026 デモ 障害時フォールバック手順

優先順位: **ローカルで本当に動いていること > 速いこと > 賢いこと**。
デモが多少遅くても、ローカル完結が崩れる選択肢は取らない。

## Tier 1: ローカル復旧（1〜2 分）

| 症状 | 復旧手順 |
|---|---|
| バックエンド応答なし | `bash scripts/demo/up.sh`（再起動）→ `bash scripts/demo/warmup.sh` |
| LLM のみ死亡（Ollama 停止等） | `ollama serve` 起動 → `ollama ps` 確認 → warmup.sh |
| TTS のみ死亡（kokoro-tts） | `docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice up -d kokoro-tts` → warmup.sh |
| STT のみ死亡 | `docker compose ... logs backend` で ONNX エラー確認 → モデル再DL（事前手順） |
| RAM 不足（モデルロード失敗） | `OLLAMA_MODEL=gemma4:e2b` に切替 → `up -d backend` → warmup.sh |

## Tier 2: クラウド版へ切替（デモ中 30 秒）

ローカルが完全に死亡し 2 分以内に復旧できない場合のみ。**「ローカル完結」の主張が崩れるため、登壇文言は「デモは録画をご覧ください」に切替えること。**

1. クラウド版キオスク URL（本番）を開く: `https://engineer-cafe.jp`（Q&A 機能が稼働中の場合）
2. または開発用: `http://<cloud-run-backend-url>` を確認する手順は `docs/DEPLOYMENT.md` 参照
3. 音声デモの代わりに **デモ録画** を再生（下記 Tier 3）

## Tier 3: デモ録画（確定フォールバック）

事前に録画済みのデモ動画を用意しておく（このスクリプトが生成する実ログベースの証跡とは別に、**画面キャプチャ動画** を 1 本）。

推奨撮影（渡航前）:
- QuickTime 画面収録で `http://localhost:3000` のデモ①→②を 1 本撮影（音声込み）
- ファイル名: `docs/demo/coscup2026/evidence/demo-recording.mov`（Git には含めない）
- 会場では画面共有 → 動画再生で代替

## 通信ゼロの証明を求められたら

`docs/demo/coscup2026/evidence/offline/` の成果物を提示:
- `offline-run.log` — Wi-Fi 切断中のデモ 2 項目完走ログ（transcript / answer / e2e_ms）
- `offline-capture.pcap` — Wi-Fi 切断中の tcpdump（外向きパケットなし）
- 再現手順: `bash scripts/demo/offline-proof.sh`（sudo 必要）

# docker/piper-plus — PiperPlus TTS アダプタ（backend /synthesize 互換）

COSCUP 2026 デモ / 本番パリティ用のローカル PiperPlus TTS サーバー。
backend `PiperPlusTTSClient`（`backend/agents/voice/clients.py`）が期待する
`POST /synthesize` 契約で合成結果（WAV）を返す。

## 構成

- ベース: `python:3.12-slim`（ARM64 / x86_64 両対応）
- TTS エンジン: `piper-plus` pip パッケージ（1.13.0・MIT）
- モデル: **tsukuyomi-chan-6lang-fp16.onnx**（39MB・MB-iSTFT・ja/en/zh/es/fr/pt）
  - ソース: https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan
  - 英語は MultilingualPhonemizer が文単位で自動判定（language_id 指定不要）
- nltk データ: g2p-en の import 時要求（averaged_perceptron_tagger / cmudict）を
  ビルド時に同梱。旧名 `averaged_perceptron_tagger.zip` も配置（g2p-en が find() で参照）

## ビルド（準備フェーズのみ・実行時はネットワーク不要）

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice \
  build piper-plus
```

モデル・辞書データはビルド時に取得されイメージ内に焼き込まれる。
**実行時に外部ネットワークへは出ない。**

## API

| エンドポイント | 内容 |
|---|---|
| `POST /synthesize` | `{"text": "...", "language": "en"}` → `audio/wav`（16bit PCM・22050Hz） |
| `GET /api/voices` | voice 一覧（compose healthcheck で使用） |

## 検証（2026-08-06）

- 英語合成: Q1〜Q3 デモ回答文で 137〜171ms（転送込み）。Kokoro 比 15-20 倍高速
- 日本語合成: 動作確認済み（デモでは未使用）
- 割り込み: 合成中キャンセル 10/10
- オフライン: Wi-Fi 切断 + tcpdump 0 パケットで完走（evidence/offline2/）

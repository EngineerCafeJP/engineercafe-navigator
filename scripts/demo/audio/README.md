# Demo Audio Fixtures

COSCUP 2026 デモで使用するテスト用 WAV の生成手順。
**WAV バイナリはコミットしない**（`.gitignore` 対象。スクリプトが自動生成する）。

## 1. デモ質問 2 件の WAV 生成（macOS `say` コマンド）

`offline-proof.sh` と `latency.sh` が読み込む WAV を生成する:

```bash
cd scripts/demo/audio

say -v Samantha -o q1_what_can_i_do.wav --data-format=LEI16@16000 \
  "What can I do at Engineer Cafe?"

say -v Samantha -o q2_where_is_toilet.wav --data-format=LEI16@16000 \
  "Where is the toilet?"
```

- `offline-proof.sh` は両ファイルが無い場合に自動生成する。
- `-v Samantha` は macOS 標準の英語音声。一覧は `say -v '?'` で確認できる。
- Qwen3-ASR は 16kHz にリサンプリングするため、16k/22.05k/44.1k いずれでも可。

## 2.（任意）ノイズテスト用 WAV（ffmpeg / sox）

STT の耐ノイズ性確認用。結果は `docs/demo/coscup2026/evidence/noise/` に保存する
（本レポートの「5. 会場ノイズ耐性」参照）。

```bash
# ピンクノイズを SNR 5dB で重畳
ffmpeg -y -f lavfi -i "anoisesrc=color=pink:duration=3:amplitude=0.5" -ar 16000 -ac 1 noise.wav
sox -m -v 1 q1_what_can_i_do.wav -v 0.56 noise.wav q1_snr5.wav   # 0.56 = 10^(-5/20)
```

## 3. 生成物の扱い

- `*.wav` はコミットしない（ルート `.gitignore` に追記済み）。
- デモ当日は Wi-Fi 切断前に生成済みであること。

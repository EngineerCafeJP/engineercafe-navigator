# piper-plus Phase 1 ベンチマーク結果

日時: 2026-04-01 01:26:01
環境: macOS ARM64 (Apple Silicon)
piper バイナリ: /Users/user/piper-plus/piper/bin/piper
日本語モデル: tsukuyomi-chan-6lang-fp16.onnx
英語モデル: en_US-lessac-medium.onnx

## レイテンシ測定結果

| 文字数 | piper-plus (avg) | piper-plus (min) | VOICEVOX (avg) | VOICEVOX (min) | 改善率 (avg) |
|--------|-----------------|-----------------|---------------|---------------|-------------|
| 10文字 | 0.608s | 0.580s | 0.348s | 0.337s | -75.0% |
| 50文字 | 0.741s | 0.717s | 1.387s | 1.378s | +46.6% |
| 200文字 | 1.218s | 1.181s | 5.135s | 5.099s | +76.3% |

## 受入基準チェック

| 基準 | 結果 | 判定 |
|------|------|------|
| レイテンシ 50%以上改善 (50文字) | piper 0.741s / VOICEVOX 1.387s (+46.6%) | ⚠️ 惜しくも未達 |
| レイテンシ 50%以上改善 (200文字) | piper 1.218s / VOICEVOX 5.135s (+76.3%) | ✅ PASS |
| 日本語音声品質「違和感なく聞ける」 | 違和感はないが自然ではない。VOICEVOX の方が明らかに自然 | ❌ FAIL |
| 英語音声品質 | piper lessac は自然さで Kokoro に劣る | ❌ FAIL |
| 既存サービスとの共存 | env var 切替で実装済み | ✅ PASS |

## 主観評価まとめ

| モデル | 自然さ | 備考 |
|--------|--------|------|
| piper tsukuyomi-chan | △ | 違和感はないが自然ではない |
| piper css10 | △ | 同上 |
| VOICEVOX ずんだもん | ◎ | 明らかに自然・高品質 |
| piper en_US-lessac | △ | Kokoro より劣る |
| Kokoro TTS | ○ | 自然な英語音声 |

## Phase 1 結論

**piper-plus の採用は現時点では推奨しない。**

- レイテンシは長文で大幅改善 (+76%) されるが、短〜中文では優位性が小さい
- 音声品質が VOICEVOX / Kokoro を下回り、ユーザー体験の低下が見込まれる
- 日本語モデルが2種類のみで選択肢が少ない
- **長文レスポンスの高速化が必要な場面では、テキスト分割 + VOICEVOX の並列処理など別アプローチを先に検討すべき**

## 代替案

| 案 | 概要 | 期待効果 |
|----|------|---------|
| A. テキスト分割並列処理 | 長文を文単位で分割して VOICEVOX に並列投入 | 200文字でも 1-2s 以内を狙える |
| B. piper-plus を英語のみに限定採用 | 英語は Kokoro より速いため英語専用に切替 | 英語レイテンシ 3倍改善 |
| C. Cloud Run の VOICEVOX 最適化 | CPU数・メモリ増強、ウォームアップ改善 | コールドスタート問題の根本解決 |

## 生成サンプル

### 日本語サンプル（エンジニアカフェ想定ユースケース）

| # | テキスト | piper tsukuyomi | piper css10 | VOICEVOX |
|---|---------|----------------|-------------|----------|
| 01 | いらっしゃいませ、エンジニアカフェへようこそ！ | [ja_01_piper_tsukuyomi.wav](tts_samples/ja_01_piper_tsukuyomi.wav) | [ja_01_piper_css10.wav](tts_samples/ja_01_piper_css10.wav) | [ja_01_voicevox.wav](tts_samples/ja_01_voicevox.wav) |
| 02 | ご利用ありがとうございます。 | [ja_02_piper_tsukuyomi.wav](tts_samples/ja_02_piper_tsukuyomi.wav) | [ja_02_piper_css10.wav](tts_samples/ja_02_piper_css10.wav) | [ja_02_voicevox.wav](tts_samples/ja_02_voicevox.wav) |
| 03 | 何かお手伝いできることはありますか？ | [ja_03_piper_tsukuyomi.wav](tts_samples/ja_03_piper_tsukuyomi.wav) | [ja_03_piper_css10.wav](tts_samples/ja_03_piper_css10.wav) | [ja_03_voicevox.wav](tts_samples/ja_03_voicevox.wav) |
| 04 | エンジニアカフェは、福岡市が運営するエンジニア向けの施設です。コワーキングスペースとして利用できます。 | [ja_04_piper_tsukuyomi.wav](tts_samples/ja_04_piper_tsukuyomi.wav) | [ja_04_piper_css10.wav](tts_samples/ja_04_piper_css10.wav) | [ja_04_voicevox.wav](tts_samples/ja_04_voicevox.wav) |
| 05 | イベントの開催スケジュールについては、公式ウェブサイトをご確認ください。 | [ja_05_piper_tsukuyomi.wav](tts_samples/ja_05_piper_tsukuyomi.wav) | [ja_05_piper_css10.wav](tts_samples/ja_05_piper_css10.wav) | [ja_05_voicevox.wav](tts_samples/ja_05_voicevox.wav) |
| 06 | 会議室の予約は、受付にてお申し込みいただけます。 | [ja_06_piper_tsukuyomi.wav](tts_samples/ja_06_piper_tsukuyomi.wav) | [ja_06_piper_css10.wav](tts_samples/ja_06_piper_css10.wav) | [ja_06_voicevox.wav](tts_samples/ja_06_voicevox.wav) |
| 07 | 本日のイベントは午後2時から始まります。参加ご希望の方は、エントランスにてスタッフにお声がけください。お飲み物は自由にご利用いただけます。 | [ja_07_piper_tsukuyomi.wav](tts_samples/ja_07_piper_tsukuyomi.wav) | [ja_07_piper_css10.wav](tts_samples/ja_07_piper_css10.wav) | [ja_07_voicevox.wav](tts_samples/ja_07_voicevox.wav) |
| 08 | プログラミングの学習や技術書の閲覧、勉強会の開催など、エンジニアの皆さんの活動を幅広くサポートしております。 | [ja_08_piper_tsukuyomi.wav](tts_samples/ja_08_piper_tsukuyomi.wav) | [ja_08_piper_css10.wav](tts_samples/ja_08_piper_css10.wav) | [ja_08_voicevox.wav](tts_samples/ja_08_voicevox.wav) |
| 09 | Wi-Fiのパスワードは EngineerCafe2024 です。ゲストネットワークもご利用いただけます。 | [ja_09_piper_tsukuyomi.wav](tts_samples/ja_09_piper_tsukuyomi.wav) | [ja_09_piper_css10.wav](tts_samples/ja_09_piper_css10.wav) | [ja_09_voicevox.wav](tts_samples/ja_09_voicevox.wav) |
| 10 | Pythonや JavaScript、Go言語など様々な技術スタックの勉強会を毎週開催しています。ぜひご参加ください！ | [ja_10_piper_tsukuyomi.wav](tts_samples/ja_10_piper_tsukuyomi.wav) | [ja_10_piper_css10.wav](tts_samples/ja_10_piper_css10.wav) | [ja_10_voicevox.wav](tts_samples/ja_10_voicevox.wav) |

### 英語サンプル

| # | テキスト | piper lessac | Kokoro |
|---|---------|-------------|--------|
| 01 | Welcome to Engineer Cafe! How can I help you today? | [en_01_piper_lessac.wav](tts_samples/en_01_piper_lessac.wav) | [en_01_kokoro.wav](tts_samples/en_01_kokoro.wav) |
| 02 | The coworking space is open from 10 AM to 10 PM on weekdays. | [en_02_piper_lessac.wav](tts_samples/en_02_piper_lessac.wav) | [en_02_kokoro.wav](tts_samples/en_02_kokoro.wav) |
| 03 | We host weekly tech meetups covering Python, JavaScript, and cloud technologies. Feel free to join us! | [en_03_piper_lessac.wav](tts_samples/en_03_piper_lessac.wav) | [en_03_kokoro.wav](tts_samples/en_03_kokoro.wav) |

## モデル情報

| モデル | 言語 | 話者 | サイズ感 |
|--------|------|------|---------|
| tsukuyomi-chan-6lang-fp16 | 日本語 | 月詠みらい(v2) | FP16 ONNX |
| css10-ja-6lang-fp16 | 日本語 | css10 JP | FP16 ONNX |
| en_US-lessac-medium | 英語 | Lessac | ONNX medium |

## 備考

- VOICEVOX / Kokoro の計測には Docker 起動が必要 (`docker-compose up voicevox kokoro-tts`)
- `--all` フラグで全サービスを含む比較が可能
- Cloud Run コールドスタートは Phase 2 で別途計測
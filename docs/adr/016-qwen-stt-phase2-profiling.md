# ADR 016: Qwen STT Phase 2 Profiling

作成日: 2026-04-24
更新日: 2026-04-25 (Phase B-1 production 実測結果追記)

## ステータス

**完了**: Phase A profiling (PR #558) + Phase B-1 Qwen-only fast-path (PR #560) 両方実装・
deploy・live 実測済み。目標 p50 3.1s を上回る 2827ms (34% 短縮) を達成。
Epic #474 Exit Criterion `/api/voice p95 < 10s` 達成 (p95 = 7035ms)。

## 背景

ADR 010 では Qwen3-ASR の ONNX/INT4 化を No-Go とした。理由は、Qwen3-ASR が
`generate()` ベースの autoregressive model であり、Optimum の標準 export では扱えない
ためである。ローカル PyTorch warm inference は約 0.3 秒で、Cloud Run の約 8 秒前後の
STT latency は Qwen 推論本体以外にある可能性が高い。

本番は `STT_PROVIDER=qwen-primary` で、Qwen と Vosk fallback の winner-race が既に実装
されている。ただし本番でどちらが勝っているか、Vosk の cancel が latency にどう効いて
いるか、cold model load がどの程度残っているかを structured log で継続的に確認できて
いなかった。

また本番環境には `QWEN_STT_TIMEOUT=true` という誤った値が入っていた。`qwen-primary`
初期化時に数値変換するため、この値は起動時または agent 初期化時の失敗原因になる。

## 決定

Phase A では以下を実施する。

- `QWEN_STT_TIMEOUT` は正の有限数だけを受け付け、不正値は 10 秒へ fallback する。
- `backend.observability.structured_logger.log_stt_event()` で STT profiling 用 JSON log を
  stdout に出す。
- `qwen-primary` の各 request に `stt_trace_id` を付与し、以下のイベントを記録する。
  - `stt_qwen_start`
  - `stt_qwen_complete` with `stt_qwen_duration_ms`
  - `stt_vosk_start`
  - `stt_vosk_complete` with `stt_vosk_duration_ms`
  - `stt_winner` with `stt_winner` and `stt_overall_duration_ms`
  - `stt_model_load_complete` with `stt_model_load_duration_ms`
- `scripts/profile_stt.sh` で Cloud Run live `/api/voice` を 20 回、4 秒間隔で叩き、
  Cloud Logging の `jsonPayload.event=~"stt_.*"` を CSV と Markdown に保存する。

## Profile 結果

### Phase A baseline (rev `00099-rx2`, 2026-04-24)

`QWEN_STT_TIMEOUT=10` 更新 + Phase A structured logger deploy 後、
`scripts/profile_stt.sh --iterations 20 --sleep 4` を実行。

Source: `backend/tests/reports/stt-profile-20260424T115017Z.md`

| Metric | count | p50 ms | p90 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| request_total | 20 | 4522 | 8853 | 43248 | 71850 |
| stt_overall | 19 | 4318 | 4562 | 11302 | 71551 |
| qwen_inference | 19 | 3098 | 3279 | 10050 | 70791 |
| vosk_inference | 19 | 4317 | 4560 | 11224 | 70790 |
| model_load | 1 | 33022 | 33022 | 33022 | 33022 |

winners: qwen=18, vosk=1

### Phase B-1 results (rev `00100-ltt`, 2026-04-25 post merge #560)

Phase B-1 `Qwen-only fast-path with Vosk cancellation` (PR #560) deploy 後、同条件で再計測。

Source: `backend/tests/reports/stt-profile-20260424T154617Z.md`

| Metric | count | p50 ms | p90 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| request_total | 20 | 2978 | 3172 | 7035 | 78340 |
| stt_overall | 19 | 2827 | 2999 | 10536 | 78192 |
| qwen_inference | 19 | 2826 | 2997 | 9910 | 71935 |
| vosk_inference | 19 | 2826 | 2997 | 3262 | 5458 |
| model_load | 1 | 35365 | 35365 | 35365 | 35365 |

winners: qwen=18, vosk=1

### 改善サマリ (Phase A → Phase B-1)

| Metric | Phase A p50 | Phase B-1 p50 | 短縮 |
| --- | ---: | ---: | ---: |
| request_total | 4522 | **2978** | **-34%** |
| stt_overall | 4318 | **2827** | **-34%** |
| qwen_inference | 3098 | 2826 | -9% |
| request_total p95 | 43248 | **7035** | **-84%** |

**重要**: Phase B-1 の狙い通り `stt_overall p50 (2827ms) ≈ qwen_inference p50 (2826ms)` で
**差 1ms** に収束。Qwen 勝利時に Vosk 完了を待たず即 return する fastpath が完全機能。

Epic #474 Exit Criterion `/api/voice p95 < 10s` はこれで達成 (p95 = 7035ms)。

## Phase B 判断基準

Profile 結果に基づいて Phase B を 1 つだけ選ぶ。

- Qwen が安定して速く、Vosk が CPU 競合または不要な待ちを生んでいる場合:
  B-1 `Qwen-only path` を選ぶ。Vosk は Qwen failure / timeout 後に fallback-only とする。
- model load や CPU 推論そのものが支配的で、alpha 期間のコスト承認が取れる場合:
  B-2 `Cloud Run GPU Spike` を検討する。ただし GPU cost と region は事前承認必須。
- Qwen 品質または runtime packaging がボトルネックで、Whisper の品質/速度が勝る場合:
  B-3 `Whisper-large-v3-turbo` spike を検討する。

Phase A profile (`backend/tests/reports/stt-profile-20260424T115017Z.md`) では、STT latency は
以下だった。

| Metric | p50 ms |
| --- | ---: |
| stt_overall | 4318 |
| qwen_inference | 3098 |
| vosk_inference | 4317 |

winner 分布は qwen=18、vosk=1 で、Qwen が多くの request で勝っていた。一方で
`stt_overall` は `vosk_inference` に近く、Qwen 勝利後も Vosk 側の完了待ちまたは CPU 競合
が残っていた。したがって Phase B-1 を採用し、Qwen success path では Vosk fallback task を
cancel して即 return する。Qwen failure / timeout の場合だけ Vosk を sequential に起動する。

期待値は `stt_overall` p50 が `qwen_inference` p50 に近い約 3.1 秒となること、つまり Phase A
の約 4.3 秒から約 1.2 秒短縮すること。merge / deploy 後に
`scripts/profile_stt.sh --iterations 20 --sleep 4` を再実行し、この ADR に Phase B-1 実測値を
追記する。

**実測結果 (rev `00100-ltt` 2026-04-25)**: Phase B-1 merge + deploy 後の実測で `stt_overall`
p50 は **2827ms** となり、期待値 3.1 秒を上回る改善 (-34%、Phase A 比 -1491ms)。
`stt_overall - qwen_inference` 差は 1ms に収束し、Qwen 勝利時の Vosk 完了待ちが完全に
解消されていることを実証。詳細は「Profile 結果 > Phase B-1 results」セクション参照。

## 互換性

- API response schema は変更しない。
- structured log は stdout への追加ログであり、既存 request behavior を変更しない。
- `QWEN_STT_TIMEOUT` の不正値は 10 秒に fallback するため、誤設定時の起動失敗を避ける。
- `STT_QWEN_POSTPROCESS_ENABLED` の状態は Qwen timing events と winner event に含める。

## ロールバック

問題が出た場合は、`backend/agents/stt_agent.py` の `log_stt_event()` 呼び出しと
`backend/observability/structured_logger.py` の STT helper 追加分を revert する。timeout
guard は安全側の変更であり、残しても既存挙動への影響は小さい。

## 検証方針

- Unit: `qwen-primary` が malformed `QWEN_STT_TIMEOUT=true` を 10 秒に fallback すること。
- Unit: Qwen success path が `stt_qwen_start`、`stt_qwen_complete`、`stt_winner` を emit
  すること。
- Script: `scripts/profile_stt.sh --help` が通ること。
- Production: deploy 後に `scripts/profile_stt.sh --iterations 20 --sleep 4` を実行し、
  report の p50 / p90 / p95 / max と winner 分布を本 ADR に反映すること。

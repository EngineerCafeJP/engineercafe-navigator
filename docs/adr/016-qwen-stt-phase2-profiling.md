# ADR 016: Qwen STT Phase 2 Profiling

作成日: 2026-04-24

## ステータス

採用: Phase A profiling instrumentation 後、Phase B-1 `Qwen-only path` を実装する。

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

Codex のローカル作業環境では本番 Cloud Run への env 更新、deploy、live profiling は実行
していない。`QWEN_STT_TIMEOUT` の本番値修正は、Phase A PR merge/deploy 前に terisuke /
Claude の明示的承認後、以下で行う。

```bash
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --project=aipartner-426616 \
  --update-env-vars QWEN_STT_TIMEOUT=10
```

deploy 後、以下を実行して `backend/tests/reports/stt-profile-<timestamp>.md` と CSV を
生成する。

```bash
scripts/profile_stt.sh --iterations 20 --sleep 4
```

この ADR の最終版では、生成された report から以下を転記する。

| Metric | count | p50 ms | p90 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| request_total | TBD | TBD | TBD | TBD | TBD |
| stt_overall | TBD | TBD | TBD | TBD | TBD |
| qwen_inference | TBD | TBD | TBD | TBD | TBD |
| vosk_inference | TBD | TBD | TBD | TBD | TBD |
| model_load | TBD | TBD | TBD | TBD | TBD |

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

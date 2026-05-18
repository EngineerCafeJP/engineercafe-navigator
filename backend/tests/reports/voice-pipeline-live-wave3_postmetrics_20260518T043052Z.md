# Voice Pipeline Live Preflight

- Timestamp: wave3_postmetrics_20260518T043052Z
- Backend: https://engineer-cafe-backend-639959525777.asia-northeast1.run.app
- Case set: smoke
- TTS provider: piper
- Strict Qwen primary: no
- STT warn/max: 5000ms / 10000ms
- Similarity threshold: 0.5
- Summary: 14 PASS / 4 WARN / 0 FAIL
- Detail CSV: voice-pipeline-live-wave3_postmetrics_20260518T043052Z.csv

## Gate Position

- Welcome warmup の実装を、STT初回速度の補助導線として扱う。
- GO判断は同一セッションの STT provider、LangGraph route、PiperPlus 出力で判定する。
- スライド差し替え予定のため、slide narration はこの gate から除外する。

## Latency

| Step | Count | p50 ms | p95 ms | max ms |
| --- | ---: | ---: | ---: | ---: |
| langgraph_route | 4 | 3448 | 10849 | 10849 |
| piper_answer_tts | 4 | 1374 | 3161 | 3161 |
| piper_source_tts | 4 | 381 | 459 | 459 |
| qwen_primary_stt | 4 | 8055 | 8417 | 8417 |
| warmup_ready | 1 | 162 | 162 | 162 |
| warmup_start | 1 | 162 | 162 | 162 |

## Problems

| Status | Case | Step | Expected | Actual | Notes |
| --- | --- | --- | --- | --- | --- |
| WARN | VP-BIZ-001 | qwen_primary_stt | provider=qwen-primary|vosk-fallback latency<=10000ms hard<=45000ms | provider=qwen-primary similarity=1.000 transcript=エンジニアカフェの営業時間を教えてください。 | {"success":true,"transcript":"エンジニアカフェの営業時間を教えてください。","response":null,"audioResponse":null,"audioFormat":null,"emotion":"neutral","sessionId |
| WARN | VP-FAC-001 | qwen_primary_stt | provider=qwen-primary|vosk-fallback latency<=10000ms hard<=45000ms | provider=qwen-primary similarity=1.000 transcript=Wi-Fi の接続方法を教えてください。 | {"success":true,"transcript":"Wi-Fi の接続方法を教えてください。","response":null,"audioResponse":null,"audioFormat":null,"emotion":"neutral","sessionId": |
| WARN | VP-EVT-001 | qwen_primary_stt | provider=qwen-primary|vosk-fallback latency<=10000ms hard<=45000ms | provider=qwen-primary similarity=0.974 transcript=今日開催されるイベント教えてください。 | {"success":true,"transcript":"今日開催されるイベント教えてください。","response":null,"audioResponse":null,"audioFormat":null,"emotion":"neutral","sessionId":" |
| WARN | VP-GEN-001 | qwen_primary_stt | provider=qwen-primary|vosk-fallback latency<=10000ms hard<=45000ms | provider=vosk-fallback similarity=0.606 transcript=パイソン の 仮想 環境 と な 何 です か | {"success":true,"transcript":"パイソン の 仮想 環境 と な 何 です か","response":null,"audioResponse":null,"audioFormat":null,"emotion":"neutral","sessionI |

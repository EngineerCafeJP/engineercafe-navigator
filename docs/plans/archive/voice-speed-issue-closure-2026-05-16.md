> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Voice Speed Issue Closure Note

作成日: 2026-05-16

## 結論

音声速度 Issue は、`<1.5s` 級の最終目標を達成したものとしては閉じない。
ただし、post-alpha の実測でボトルネック、改善済み範囲、残るリスクが分離できたため、
この Issue は「実測済み・残課題分割済み」として閉じる。

閉じる理由は次の 3 点。

1. STT はまだ主ボトルネックだが、TimeoutError や 30s 超の破綻は直近 gate で出ていない。
2. LangGraph route と PiperPlus TTS は post-alpha retry で実用域まで戻っており、全面刷新の根拠はない。
3. STT runtime compare で ONNX 候補の改善は見えたが、CPU path だけでは `<1.5s` 目標に届かないことも明確になった。

したがって、この Issue の close 条件は「目標速度達成」ではなく、
「現実の alpha/post-alpha 速度を記録し、P2/P3 follow-up の判断基準を確定すること」とする。

## 根拠ファイル

| Evidence | File | 結果 |
| --- | --- | --- |
| post-alpha live STT/TTS baseline | `backend/tests/reports/voice-pipeline-live-post-alpha-live-stt-tts-20260509010917.md` | `10 PASS / 2 WARN / 2 FAIL`。STT p50 `10206ms`, p95/max `12202ms`。answer TTS p50 `847ms`, p95/max `1424ms`。成功証跡ではなく、未達 baseline として扱う。 |
| post-alpha retry | `backend/tests/reports/voice-pipeline-live-post-alpha-rag-node24-deploy-retry-20260509024048.md` | `14 PASS / 4 WARN / 0 FAIL`。STT p50 `7956ms`, p95/max `8925ms`。route p50 `1635ms`, p95/max `3233ms`。answer TTS p50 `1919ms`, p95/max `2978ms`。 |
| STT live preflight | `backend/tests/reports/stt-live-preflight-post-alpha-rag-node24-stt-20260509024521.md` | gate failed。samples `9`, p50 `6877ms`, p95/max `10006ms`, over 10s `1/9` (`11.1%`), TimeoutError `0`, over 30s `0`。 |
| runtime compare 09:21 | `backend/tests/reports/stt-runtime-compare-20260509T0921Z.md` | ONNX candidate が request_total p50 `-1114ms`, p90 `-4071ms`、qwen_runtime p50 `-7358ms`, p90 `-8744ms` 改善。 |
| runtime compare 09:25 | `backend/tests/reports/stt-runtime-compare-20260509T0925Z.md` | ONNX candidate が request_total p50 `-848ms`, p90 `-3687ms`、qwen_runtime p50 `-6004ms`, p90 `-6770ms` 改善。 |
| quality gates q/m/t | `backend/tests/reports/quality-gates-live-637450e-qmt.md` | `26 PASS / 3 WARN / 3 FAIL`。TTS は `3 PASS / 3 WARN / 0 FAIL` で、JA TTS latency WARN は残るが format/生成は成立。 |
| quality gates q/m | `backend/tests/reports/quality-gates-live-cd425a3-qm.md` | `24 PASS / 1 WARN / 1 FAIL`。音声速度とは別軸の QA/memory 残件を確認。 |

## 現在地

### STT

STT は未達。post-alpha retry でも p50 は `7956ms`、STT live preflight でも p50 `6877ms`、
p95 `10006ms` で、従来の `<1.5s` 目標にも中間目標 `p50 < 3s / p95 < 5s` にも届いていない。

一方で、直近 gate のリスクシグナルは bounded である。

- TimeoutError: `0`
- 30s 超: `0`
- 10s 超: `1/9`
- p95: `10006ms`

このため、alpha/post-alpha の利用判断としては「速度は遅いが破綻は限定的」まで確認済み。
STT を全面刷新する判断材料ではなく、runtime / deployment / UX の各 follow-up へ分ける材料とする。

### TTS

TTS は主ボトルネックではない。post-alpha retry の answer TTS は p50 `1919ms`, p95 `2978ms`。
ただし quality gates の isolated TTS suite では JA short/long/trunc が `8314ms` から `11883ms`
で WARN になっており、長文・日本語 TTS の latency は P2 として残す。

### LangGraph route / answer generation

post-alpha retry の route は p50 `1635ms`, p95 `3233ms` まで戻っている。
これは STT より改善優先度が低い。quality gates の q suite には QA 正確性の FAIL が残るが、
音声速度 Issue の close blocker にはしない。

### Runtime compare

ONNX candidate は CPU path の中では改善を示した。

- 09:21 compare: request_total p50 `7442ms -> 6329ms`, p90 `10722ms -> 6651ms`
- 09:25 compare: request_total p50 `7148ms -> 6300ms`, p90 `10296ms -> 6609ms`
- qwen_runtime は約 `6.0s` から `8.7s` 改善

ただし、candidate request_total も p50 `6300ms` 前後であり、`<1.5s` 目標には届かない。
ONNX は採用候補として残せるが、この Issue 内での全面移行・全面刷新はしない。

## Close 条件

この Issue は次の条件を満たしたため close 可能。

- 実測値が日付付きレポートに残っている。
- 成功/失敗の境界が明確になっている。
  - 成功: route/TTS は post-alpha retry で hard failure なし。
  - 未達: STT は p50 6-8s 台で、速度目標未達。
- `<1.5s` 目標未達を隠さず、P2/P3 follow-up に分割した。
- Vosk early winner へ戻す、STT stack を全面差し替える、TTS を別実装へ全面移行する、といった大きい変更は close 条件に含めない。
- 今後の改善判断は「平均」ではなく p50/p95、10s 超率、TimeoutError、route/TTS regression で見る。

## 残課題

### P2: STT latency follow-up

目的: 現行構造を維持したまま p50/p95 を改善する。

判断基準:

- p50 `< 3s`
- p95 `< 5s`
- 10s 超率 `< 5%`
- TimeoutError `0`
- route/TTS regression `0`
- Vosk fallback が transcript 品質を壊すケースを増やさない

候補:

- ONNX runtime の本番採用可否を追加測定する。
- Cloud Run CPU/memory/concurrency を同一 case set で比較する。
- hedge wait / grace wait を短縮しても route 品質が落ちないか確認する。
- `stt_request_duration_ms`, `stt_qwen_runtime_duration_ms`, `stt_winner` を同一 report で継続比較する。

### P2: Japanese TTS long-tail

目的: 日本語 TTS の長文 latency WARN を減らす。

判断基準:

- JA short p95 `< 5s`
- JA long p95 `< 8s`
- audio/wav format と back-check を維持
- empty text error は 400 のまま

候補:

- 長文 chunking と cache/prefetch の追加測定。
- slide narration など静的音声は live TTS から外す。
- TTS provider を変える場合は、format/size/duration/back-check を既存 gate と同じ条件で比較する。

### P3: UX perceived latency

目的: STT 自体が遅い場合でも、受付体験の待ち時間を説明可能にする。

判断基準:

- first audible filler p95 `< 500ms`
- mic recording end から thinking state 表示 p95 `< 300ms`
- close 後の stale playback `0`
- mobile autoplay / permission failure の復帰導線あり

候補:

- browser-level timing proof を追加する。
- filler / thinking / timeout copy の表示タイミングを測る。
- streaming partial transcript は spike に留め、確定 transcript との差分制御ができるまで本線には入れない。

## 次に reopen する条件

次のいずれかを満たした場合は、この Issue ではなく follow-up issue として reopen / new issue 化する。

- STT p95 が `12s` を超える。
- 10s 超率が `10%` を継続的に超える。
- TimeoutError が再発する。
- Vosk fallback の transcript が route を誤誘導し、voice pipeline に hard FAIL が戻る。
- TTS が `audio/wav` を返さない、または answer TTS が p95 `5s` を継続的に超える。
- QA/memory quality gate の FAIL が音声経路だけで再現する。

## Issue コメント案

音声速度 Issue は、最終目標の `<1.5s` 達成ではなく、post-alpha 実測の確定と残課題分割をもって close します。

- STT は未達: live preflight p50 `6877ms`, p95 `10006ms`, over 10s `1/9`, TimeoutError `0`
- post-alpha retry は `14 PASS / 4 WARN / 0 FAIL`: route p50 `1635ms`, answer TTS p50 `1919ms`
- ONNX candidate は改善あり: request_total p50 約 `0.8s-1.1s`, p90 約 `3.7s-4.1s` 改善。ただし `<1.5s` には未達
- 残りは P2 STT latency、P2 JA TTS long-tail、P3 perceived latency に分割

この Issue では STT/TTS の全面刷新は行いません。次の判断は p50/p95、10s 超率、TimeoutError、route/TTS regression の同時条件で行います。

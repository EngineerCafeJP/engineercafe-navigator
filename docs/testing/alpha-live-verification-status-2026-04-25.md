# Alpha Live Verification Status 2026-04-25

このドキュメントは、#571 Alpha GO/NO-GO 判断のための最新の引き継ぎメモです。次回セッションでは、まずこのファイルを読んでから #571 / #575 / PR #592 を確認してください。

## 現在の結論

**NO-GO** です。

PR #592 の live verification 基盤は有効ですが、Qwen3-ASR primary の安定性、観測権限、RAGAS secret、Welcome workflow timeout、Q quality gate に未解決 blocker があります。Vosk-only には戻しません。構成方針は引き続き **Qwen3-ASR primary + Vosk fallback** です。

## 最新の実行

- PR: #592 `test(alpha): q/m/t 品質 gate を live verification に追加`
- Live run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/24929491049>
- 実行 commit: `221756ee51b84b65dd641be459a0a21e2d059e36`
- Cloud Run revision: `engineer-cafe-backend-00114-q8w`
- Cloud Run image: `engineer-cafe-backend:221756ee51b84b65dd641be459a0a21e2d059e36`
- 実行 suites: `stt,v,a,b,c,d,e,q,m,t,h-ui`
- `require_deployed_sha_match`: `true`
- runtime env:
  - `STT_PROVIDER=qwen-primary`
  - `QWEN_STT_TIMEOUT=8`
  - `STT_PRELOAD_QWEN_PRIMARY=true`
  - `TTS_PROVIDER=piper`

注意: Serena 削除と docs 更新により PR head は live run 実行 commit から進んでいます。最終 GO 証跡としては、その時点の最新 head を Cloud Run に再デプロイしてから再実行してください。

## Suite 結果

| Suite | 結果 | 内容 |
|---|---|---|
| STT preflight | FAIL | GitHub Actions の GCP service account が Cloud Logging を読めず `PERMISSION_DENIED` |
| V voice pipeline | FAIL | warmup は `ready:qwen-primary`。4 STT case 中 2 件が `vosk-fallback`、2 件 WARN |
| A voice round-trip | FAIL | `170 PASS / 7 WARN / 23 FAIL`。provider gate 追加後、40 発話中 23 件で `sttProvider != qwen-primary` |
| B routing | PASS | `64 PASS / 0 WARN / 0 FAIL` |
| C RAGAS | FAIL | workflow 上で `OPENAI_API_KEY` または `OPENROUTER_API_KEY` が取れず未評価 |
| D memory/state | PASS | `55 PASS / 0 WARN / 0 FAIL` |
| E Cloud Logging | FAIL | STT preflight と同じ Cloud Logging 権限問題 |
| Q answer quality | FAIL | `17 PASS / 0 WARN / 4 FAIL` |
| M memory quality | WARN | `4 PASS / 1 WARN / 0 FAIL`。明示記憶ではない Wi-Fi SSID を想起 |
| T PiperPlus TTS | WARN | `4 PASS / 2 WARN / 0 FAIL`。短文/長文で latency WARN |
| H-UI Welcome | FAIL | 0s/5s/10s delay すべて `page.waitForResponse` 120s timeout |

## Alpha Blockers

1. **Qwen3-ASR primary が live round-trip で維持できない**
   - V suite: 4 STT case 中 2 件が `vosk-fallback`
   - A suite: 40 発話中 23 件が provider gate で FAIL
   - fallback は機能しているが、primary として期待速度で横帯できる証明になっていない

2. **STT latency / timeout 設計が未確定**
   - A の FAIL latency はおおむね `10.7s-22.6s`
   - `QWEN_STT_TIMEOUT=8` が、UX と Qwen primary 維持の両方に対して妥当か再判断が必要

3. **Cloud Logging gate が認証不足**
   - `engineer-cafe-navigator@aipartner-426616.iam.gserviceaccount.com` に log read 権限が不足
   - `scripts/stt-live-preflight.sh` と `scripts/cloud-logging-verify.sh` が GitHub Actions で成立しない

4. **C RAGAS が未証明**
   - evaluator 用の `OPENAI_API_KEY` / `OPENROUTER_API_KEY` が workflow で利用できていない
   - C は live answer quality を見るが、live retrieval context の完全証明ではない点も継続注意

5. **Q answer quality gate に 4 FAIL**
   - route は合っているが expected facts / source / answer quality 側で落ちている

6. **Welcome 起点の H-UI workflow が timeout**
   - Welcome warmup 後の 0s/5s/10s 初回発話が 120s timeout
   - 実機音響以前に fixture audio の UI workflow gate が未成立

7. **M memory quality に WARN**
   - 明示記憶ではない Wi-Fi SSID を想起した
   - LTM 昇格条件または評価 case の期待値を再確認する

## 次回の作業順

1. 最新 PR head の通常 CI 完了を確認する。
2. Cloud Logging 権限と RAGAS secret を直す。これを直さないと live run が実装問題と環境問題で混ざる。
3. Qwen fallback 退化を切り分ける。
   - `stt_qwen_start`
   - `stt_qwen_complete`
   - `stt_winner`
   - `/api/voice` response latency
   - `sttProvider`
4. `QWEN_STT_TIMEOUT=8` のまま GO 可能か、または alpha 用 timeout / warmup / concurrency 設計を変更するか判断する。
5. Q quality 4 FAIL の answer/source/fact mismatch を修正する。
6. H-UI Welcome timeout を、STT timeout 起因か frontend wait 条件起因か分ける。
7. 最新 head を Cloud Run に再デプロイし、`require_deployed_sha_match=true` で再実行する。

## 再実行コマンド

Cloud Run の image tag が workflow SHA と一致していることを必ず確認します。

```bash
gh pr view 592 --json headRefOid,statusCheckRollup,mergeStateStatus,isDraft

gcloud run services describe engineer-cafe-backend \
  --project aipartner-426616 \
  --region asia-northeast1 \
  --format='value(status.latestReadyRevisionName,spec.template.spec.containers[0].image)'
```

Alpha Live Verification:

```bash
gh workflow run alpha-live-verification.yml \
  --ref feat/alpha-quality-gates-codex \
  -f suites=stt,v,a,b,c,d,e,q,m,t,h-ui \
  -f timestamp=alpha-live-$(date -u +%Y%m%d-%H%M%S) \
  -f require_deployed_sha_match=true
```

## 関連 Issue / PR

- #571: GO/NO-GO 親 issue
- #575: STT timeout / `/api/voice` p95 blocker
- #580: A voice round-trip
- #581: B LangGraph routing
- #582: D memory/state durability
- #583: C RAGAS live
- #585: 実機キオスク 2h / 現地 round-trip
- #586: Cloud Logging / latency / cold start
- #592: q/m/t quality gate PR

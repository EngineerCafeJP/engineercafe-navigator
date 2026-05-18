> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Post-alpha Voice / RAG / Frontend Scope Cleanup

作成日: 2026-05-09

## 目的

PR #787-#791 で本番反映された Node.js 24 / RAG mutation / voice guard の
証跡を踏まえ、次の実装スコープを voice latency、RAG/LangGraph quality、
frontend/backend 分離、運用検証の 4 本に再整理する。

## 開発環境の現在地

- `develop` は `origin/develop` と一致し、作業ツリーは clean。
- 不要 worktree は削除済み。
- 事前に残っていた tracked dirty file は復元済み。
- `.claude/worktrees/` は削除済み。
- `develop` に merge 済みの stale local branch は削除済み。
- 未マージ local branch は保全する。

## 本番実測値

対象 Cloud Run revision は `engineer-cafe-backend-00192-bzt`。
100% traffic で、`/health` は `api/supabase/llm_provider` すべて OK。

### Voice / STT / TTS

- voice pipeline retry: `14 PASS / 4 WARN / 0 FAIL`
- STT live latency gate: FAIL
  - samples: 9
  - p50: `6877ms`
  - p95/max: `10006ms`
  - winners: `qwen=4`, `vosk=5`
  - provider: `qwen-primary=4`, `vosk-fallback=5`
  - samples over 10s: `1/9`, `11.1%`
- filler live probe:
  - prior proof: p50 `164.3ms`, max `274.9ms`
  - 2026-05-09 quick probe: p50 `267.5ms`, 3/3 static audio returned
- quick chat route probe:
  - hours: `5856ms`, `BusinessInfoAgent`
  - Wi-Fi: `1070ms`, `facility-info`
  - event: `1643ms`, `EventAgent`
  - Python: `3328ms`, `general_knowledge`
  - p50: `2485.7ms`

結論: TTS/filler と route は実用域に入ったが、STT は #529 の `<1.5s`
目標に未達。体感速度の主ボトルネックはまだ初回 STT hop。

### STT latency debate

現状の体感値は、音声入力から文字起こし結果が出るまで 6-7 秒程度、その後の
回答生成と音声出力が概ね 3-5 秒程度である。後段はすでに比較的速く、
これ以上の UX 改善は first-hop STT を戻すほうが効果が大きい。

ただし、速度だけで Vosk fallback を優先するのは採用しない。直近の live voice
pipeline では Vosk の低品質 transcript が `Wi-Fi` や `Python 仮想環境` の route
を崩し、後続回答の品質を落とした。つまり今回の改善条件は「速い transcript」
ではなく「現在の route/TTS 成功率を維持した速い transcript」である。

実装候補の評価:

| Candidate | Speed | Accuracy risk | Scope judgment |
| --- | --- | --- | --- |
| Vosk early winner へ戻す | 速い場合がある | 高い。route 誤判定の再発リスク | 不採用 |
| Qwen hedge/grace 再調整 | 中 | 低〜中。既存構造を活かせる | 最初に実施 |
| audio conversion / model runtime 分解計測 | 改善余地の特定 | 低 | 必須 |
| Cloud Run CPU/memory/concurrency tuning | 中 | 低 | 計測後に実施 |
| GPU/remote STT spike | 高い可能性 | 中。運用・コスト・外部依存 | CPU path 不足時に比較 |
| streaming partial transcript | 体感改善大 | 中。確定 transcript との差分制御が必要 | UX spike として後段 |

次セッションでは、#529 を P1-A として、`stt_overall` を
audio conversion、Qwen inference、hedge wait、Vosk fallback、HTTP request total に
再分解する。最終 target `<1.5s` は維持するが、まず post-alpha の現実的な中間ゲートとして
`p50 < 3s`、`p95 < 5s`、route/TTS regression 0 を置く。

## RAG / LangGraph / Knowledge Ingestion

ADR 020 の mutation contract は本番で確認済み。

- Markdown/PDF preview: dry-run
- upload: YAML と同じ category-aware chunk planning
- create/update: embedding 欠落時は保存前に reject
- uploaded document: `entry_id` / `document_id` / chunk metadata 付与
- update/delete: RAG retrieval visible state まで検証済み
- live upload/update/delete/chat retrieval: PASS

残る未完了:

- bilingual ingestion
- metadata schema validation
- event KB live bridge / ICS -> KB cron sync
- abstract EN membership query の enhanced_rag hit
- rerank / cross-encoder / D-RAG の quality-vs-latency 評価
- RAGAS groundedness / hallucination / toxicity の実効ゲート化

RAGAS の直近有効レポートは 2026-04-27 で全言語 target PASS だが、
`ragas_context_source=golden_dataset` であり、context_precision /
faithfulness は `0.0000` 表示。live source metadata gate はあるが、live
retrieved chunks に対する groundedness gate ではない。

## Issue 再整理

### P1-A: Voice first-hop latency and resilience

- #529: STT latency `<1.5s` 未達。最優先。
- #611: static filler は速いが、first-audible UX 定義と browser timing proof が未完。
- #584: network/mic/autoplay/silence/noise/long utterance edge-case proof が未完。
- #774: onsite hardening。M5Stack、DB/cron load、TTS provider fault を実機で確認。
- #763/#762/#770/#399: frontend voice UI の follow-up。

### P1-B: RAG / LangGraph answer quality

- #540: ingestion hardening は Phase 0/1 一部完了。bilingual/schema/RAGAS gate が残る。
- #567: abstract EN membership query の retrieval miss。
- #398: multilingual answer stability。
- #514: rerank / cross-encoder。
- #518: hallucination / groundedness / toxicity metrics。
- #517: event KB live bridge。
- #655: LangGraph memory recall WARN。
- #511: 127-case RAGAS / CI gate 実効化。
- #380: D-RAG spike。

### P1-C: Frontend/backend separation

- #358: `/api/qa` proxy 廃止検討が既存の入口。
- 現状 Next.js route handlers は `frontend/src/app/api` に 29 files / 1797 LOC。
- まず API proxy 削減と認証/CORS設計を決める。
- Next -> Vite/React 移行は、proxy 廃止後に判断する。

### Closed / Done

- #668: Node.js 20 GitHub Actions deprecation は PR #787-#790 と develop CI
  run `25588854013` で完了済み。再オープン不要。

## Frontend: Next.js から React/Vite へ置き換えるべきか

認識は半分正しい。フロントとサーバーを完全分離する方向は妥当だが、
削減効果の本体は「Next をやめること」ではなく、`src/app/api` の BFF/proxy
を backend へ寄せて消すこと。

現在 Next は UI shell だけでなく、次を担っている。

- backend API key の秘匿
- Vercel -> Cloud Run proxy
- voice / qa / reception / admin knowledge API の変換
- admin/cron/monitoring middleware
- CSP/security headers
- PDF worker copy webpack hook

Next static export は動的 route handlers、Request/Cookies、server actions、
headers/rewrites 等に制約がある。Vite は SPA と dev proxy には向くが、本番
proxy/secret boundary は持たない。したがって移行順は:

1. backend に公開 API / short-lived token / CORS / rate-limit を設計する。
2. frontend call sites を backend 直呼び client に寄せる。
3. `src/app/api` を段階削除する。
4. Next を client-only shell として残すか、Vite/React へ移すかを測定で決める。

## 次の実装スコープ

1. STT latency root-cause branch
   - qwen/vosk winner trace の最新再計測
   - CPU inference / conversion / hedge / request budget の分解
   - 精度を落とす Vosk early-winner は避け、Qwen 品質を維持したまま speed を戻す
   - #529 の final acceptance は `<1.5s` を維持し、中間ゲートを `p50 < 3s`, `p95 < 5s` に置く
   - CPU path だけで不足する場合は GPU/remote STT/streaming partial transcript を比較

2. Voice UX proof branch
   - first audible timing を browser-level で測る
   - late filler / stale playback / close 後再生なしを regression 化
   - #611/#584/#774 の proof checklist を issue comment に集約

3. RAG quality gate branch
   - live retrieved contexts を使う RAGAS/LLM judge gate を追加
   - #567 の raw similarity / source selection trace を追加
   - #540 の bilingual/schema 残件を独立 issue に分割

4. Frontend separation ADR
   - #358 を ADR 化
   - backend auth/CORS 方針を決定
   - `/api/qa` -> `/api/chat` 直接化から始め、`/api/voice` と admin knowledge は後段に分ける
   - ADR 021 に従い、Next -> Vite/React 移行は `src/app/api` 削除後の build-tool 判断にする

5. Documentation hygiene
   - `docs/STATUS.md` を正本に維持
   - alpha 系の過去 plan は archive 候補
   - runbook は「どの live script をいつ使うか」に集約

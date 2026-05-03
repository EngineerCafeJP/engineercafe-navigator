# ADR 019: Alpha Live RAGAS Case Accounting

## ステータス

Accepted / implemented by PR #692

## 日付

2026-05-03

## 背景

2026-05-03 の `alpha-live-verification` C-127 run `25268597241` で、`alpha-127`
を指定したにもかかわらず artifact の `suite_coverage.requested_total_cases` が `85`
になった。

期待値と実績は次の通り。

| Language | Expected | Reported requested/evaluated |
| --- | ---: | ---: |
| ja | 80 | 38 |
| en | 23 | 23 |
| zh | 12 | 12 |
| ko | 12 | 12 |
| total | 127 | 85 |

ローカル dataset は `backend/tests/fixtures/golden_datasets/ground_truth.json` に
127 ケースを保持しており、`alpha-127` manifest も `ja=80, en=23, zh=12, ko=12`
をロードしている。したがって、これは dataset selection の問題ではなく live API
評価ハーネスの accounting 問題である。

PR #692 でこの accounting defect は修正済み。post-#692 validation run `25270459825`
では `suite_coverage.requested_total_cases=127` を保持し、live `/api/chat` 失敗は
`collection_errors` として artifact に残った。ただし同 run は `/api/chat` `429 Too Many Requests`
により `evaluated=35`, `collection_errors=92` であり、C-127 completion / alpha GO proof ではない。
429 collection blocker は #694 / PR #695 で別途対応し、post-#695 rerun 待ち。

現在の `backend/evaluation/run_live_api_eval.py` は `/api/chat` collection phase で
例外が出たケースをログに出すだけで report から落とす。その後
`requested_case_count = len(cases)` としており、ここでの `cases` は manifest 件数ではなく
collection に成功した API response 件数である。このため、API call failure が
「評価失敗」ではなく「存在しなかったケース」として扱われ、127-case gate の信頼性を失わせる。

## 決定

Alpha live RAGAS gate では、manifest/request accounting と RAGAS evaluable response
accounting を分離する。

- `requested_case_count` は manifest で選択されたケース数に固定する。
- `/api/chat` collection に失敗したケースは report から落とさず、`collection_errors`
  として case id / language / category / question / error type / message を保存する。
- `api_failed_case_count` と `collection_error_count` を per-language result に追加する。
- `suite_coverage.requested_total_cases` は manifest request count の合計にする。
- `evaluation_complete` は `evaluated_case_count == requested_case_count` に加えて
  `collection_error_count == 0` を要求する。
- `alpha_release_gate_met` は collection error が 1 件でもあれば false にする。

この変更により、`alpha-127` は API failure があっても `requested_total_cases=127`
を保持し、失敗は `evaluation_complete` / `collection_errors` として見える。

## 採用理由

Alpha gate は「評価できたケースの平均品質」だけでなく「予定した release-blocking ケースを
すべて実際に試したか」を証明する必要がある。

API failure を report から落とすと、障害が少なく見えるだけでなく、言語別 coverage の欠損も
見落とす。今回の run では欠損 42 件がすべて日本語であり、JA answer quality の判断にも影響する。

manifest accounting を正にすることで、以後の triage は次の 3 種類に分離できる。

- coverage failure: workflow / manifest / language selection が正しくない
- collection failure: live `/api/chat` が timeout / HTTP error / auth error を返す
- quality failure: API response は得られたが RAGAS / source gate が落ちる

## 代替案

### API failure を retry して成功したケースだけ評価する

短期的には pass 率が上がる可能性があるが、long-tail timeout や backend instability を隠す。
retry は別途導入してよいが、最終 report には初回失敗と retry 成否を残す必要がある。

### `requested_case_count` の名前だけ `collected_case_count` に変える

既存 artifact の意味は正確になるが、127-case gate の release proof にはならない。
Alpha gate では manifest 件数を primary accounting とする必要があるため不採用。

### Collection failure を skipped として扱う

`skipped_case_count` だけでは、RAGAS evaluator の skip と live API collection failure が混ざる。
原因別の修正ができなくなるため、`collection_errors` として別に保持する。

## 実装影響

- `backend/evaluation/run_live_api_eval.py`
  - per-language manifest count を collection 前に保存する。
  - API call exception と missing ground truth を `collection_errors` に保存する。
  - per-language result に `api_failed_case_count`, `collection_error_count`,
    `collection_errors` を追加する。
  - `evaluation_complete` と text report に collection error を表示する。
- `backend/tests/evaluation/test_ragas_live_case_suites.py`
  - `alpha-127` で 1 件の API failure が起きても `suite_coverage.requested_total_cases`
    が `127` のままになる regression test を追加する。
  - 同時に `evaluation_complete=false` と `alpha_release_gate_met=false` を確認する。

## 検証方針

1. Unit:
   `uv run --extra evaluation pytest tests/evaluation/test_ragas_live_case_suites.py -q`
2. Harness dry proof:
   `alpha-127` manifest が `127` / `80,23,12,12` を返すことを確認する。
3. Live:
   `alpha-live-verification.yml` を `suites=c-127`, `require_deployed_sha_match=true`,
   `expected_backend_sha=<current Cloud Run backend SHA>` で再 dispatch する。
4. Artifact:
   `suite_coverage.requested_total_cases=127` であること、collection failure があれば
   `collection_errors` と `evaluation_complete=false` に出ることを確認する。

## 実装・検証結果

- PR: <https://github.com/EngineerCafeJP/engineercafe-navigator/pull/692>
- Merge SHA: `d74264e808e9b2a0244d3a1a9e5dfe12671530ea`
- Live validation run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25270459825>
- Result:
  - `case_suite`: `alpha-127`
  - `suite_coverage.expected_total_cases`: `127`
  - `suite_coverage.requested_total_cases`: `127`
  - evaluated cases: `35`
  - collection errors: `92`
  - API failed cases: `92`
  - main failure mode: live `/api/chat` `429 Too Many Requests`

This validates the ADR decision: manifest/request accounting now remains `127` even when live API
collection fails. It also separates the next blocker cleanly: collection reliability / rate-limit
pacing, not manifest accounting.

## ロールバック

この変更は evaluation harness artifact schema の追加であり、product runtime には影響しない。
問題が出た場合は `run_live_api_eval.py` の accounting change を revert すれば、既存の
collection-success-only report に戻せる。ただし、その状態の C-127 result は alpha GO 証跡として
採用しない。

## 現在の実装メモ

ADR 019 itself is implemented and #691 is closed. Remaining C-127 proof depends on #694 / PR #695
and a post-#695 `suites=c-127` rerun that reaches `evaluated=127` and `collection_errors=0`.

## 2026-05-03 Reset 追記

Post-#695/#701 run `25274709049` reached the accounting bar:

- `case_suite`: `alpha-127`
- requested cases: `127`
- collected cases: `127`
- evaluated cases: `127`
- collection errors: `0`
- RAGAS errors: `0`
- provider: direct OpenAI
- model: `gpt-5.2-2025-12-11`

This closes the original accounting and collection-completion concern for ADR 019. The remaining
C alpha blocker is no longer "did the harness really test 127 cases?" but "did the product answer and
source those 127 cases well enough?"

Current remaining C failures from that run:

- JA answer correctness: `0.5671`, target `0.85`
- EN answer correctness: `0.6914`, target `0.75`
- KO source gate: `gt-113` returned `[fallback]` instead of `enhanced_rag`, `knowledge_base`, or
  `knowledge_base_cached`

Therefore, future C triage should not reopen ADR 019 unless accounting regresses. Track product
quality/source defects in #583/#672.

## 参照

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25268597241>
- Validation run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25270459825>
- Issue: <https://github.com/EngineerCafeJP/engineercafe-navigator/issues/691>
- PR: <https://github.com/EngineerCafeJP/engineercafe-navigator/pull/692>
- Follow-up rate-limit issue: <https://github.com/EngineerCafeJP/engineercafe-navigator/issues/694>
- Follow-up rate-limit PR: <https://github.com/EngineerCafeJP/engineercafe-navigator/pull/695>
- `backend/evaluation/run_live_api_eval.py`
- `backend/tests/evaluation/test_ragas_live_case_suites.py`
- `backend/tests/fixtures/golden_datasets/ground_truth.json`

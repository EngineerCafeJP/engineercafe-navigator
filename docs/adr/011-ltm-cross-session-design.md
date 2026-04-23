# ADR 011: LTM 跨セッション recall の設計修正

## ステータス

採用

## 日付

2026-04-22

## 背景

Cloud Run で以下の長期記憶フラグを有効化しても、同じ `visitor_id` の別セッションで名前を想起できない問題が確認された。

- `ENABLE_MEMORY_CANDIDATES=true`
- `ENABLE_MEMORY_PROMOTION=true`
- `ENABLE_LONG_TERM_MEMORY_RERANK=true`

検証シナリオでは、Session A で「私の名前は田中花子です。覚えてください」と伝えた後、Session B で「私の名前を覚えていますか？」と聞いても、回答に田中花子が含まれなかった。

## 問題

原因は単一の flag 設定漏れではなく、LTM 書き込み設計にある。

1. Candidate pipeline 有効時に legacy direct write が完全に無効化される。
2. Promoter は `candidate_count >= 2` または `repeat_count_sum >= 2` を要求するため、単発の明示記憶要求が昇格しない。
3. `explicit_remember` fast-path が抽出揺れや信頼度で機能しないケースがある。
4. `store_with_retry` が内部で singleton `get_store()` を使い、LangGraph から注入された `runtime.store` を迂回し得る。
5. retry lambda 内で key/value を生成すると、接続エラー retry 時に同一事実が別 key として書かれる可能性がある。

## 決定

以下の設計に変更する。

1. Candidate pipeline は shadow write として常に候補を保存する。
2. Candidate 有効時でも、即時 recall が必要な事実は LTM に直接保存する。
3. 即時 LTM 書き込み対象は、次の 2 条件のいずれかを満たす候補とする:
   - `type == "explicit_remember"`、または `query` / `evidence` に明示記憶要求キーワード（「覚えて」「記憶して」「remember」等）が含まれ、かつ `confidence >= 0.8`
   - `type == "visitor_name"` かつ `confidence >= 0.9`

   実装は `backend/workflows/main_workflow.py` の `_is_fast_path_memory()` を参照。ADR 012 の connection pool 導入後も fast-path 判定そのものは本 ADR の条件のまま。
4. Promoter は単発 `explicit_remember` と高信頼 `visitor_name` を昇格できる。
5. `store_with_retry` は `store=` を受け取り、`runtime.store` を優先する。
6. LTM 書き込みの key/value は retry lambda の外で生成し、retry 中の冪等性を保つ。

## 採用理由

LTM recall はユーザーが「覚えて」と明示した情報に対して、次セッションで即座に効く必要がある。全てを Promoter の反復回数に委ねると、名前や明示要求のような P0 体験が壊れる。

一方で全候補を即 LTM に入れるとノイズや誤抽出が増えるため、即時書き込みは低揮発・高信頼なものに限定する。その他の候補は従来通り Promoter が反復性を見て昇格させる。

## 代替案

### 代替案 A: Promoter の閾値だけ下げる

全 candidate の単発昇格が増え、ノイズが LTM に入りやすい。今回は不採用。

### 代替案 B: Candidate pipeline を無効化して legacy direct write に戻す

短期的には recall するが、段階昇格・重複抑制・rerank の改善余地を失う。今回は不採用。

### 代替案 C: explicit_remember だけ直接保存する

名前のような高信頼 PII が単発で recall できない可能性が残る。`visitor_name confidence>=0.9` も対象に含める。

## 互換性

- `ENABLE_MEMORY_CANDIDATES=false` の場合は legacy direct write を維持する。
- `ENABLE_MEMORY_CANDIDATES=true` の場合も candidate 保存は維持する。
- 新しい direct fast-path は対象 type を限定するため、既存の低信頼候補の挙動は変えない。
- `store_with_retry(store=None)` は従来通り singleton store を使う。

## ロールバック

問題が出た場合は以下で段階的に戻せる。

1. `ENABLE_MEMORY_PROMOTION=false` で Promoter 昇格を止める。
2. `ENABLE_MEMORY_CANDIDATES=false` で legacy direct write のみに戻す。
3. 必要なら本 ADR の fast-path commit を revert し、LTM 書き込みを旧設計へ戻す。

## 検証方針

- Unit: Promoter が単発 `explicit_remember` と高信頼 `visitor_name` を promote すること。
- Workflow: Candidate 有効時も fast-path LTM write が走ること。
- Retry: LTM 書き込み retry が同一 key/value を使うこと。
- Live: Cloud Run deploy 後、Session A で名前を覚えさせ、Session B で同じ `visitor_id` から名前を聞いて「山田」が含まれること。

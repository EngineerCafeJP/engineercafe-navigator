> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Alpha Fast Response Implementation Plan

Last updated: 2026-04-30

## 結論

Alpha Phase 4 の最初の実装対象は、Welcome UX ではなく次の 2 件に固定する。

1. identity / help / capability 質問を deterministic fast path にする。
2. General fallback を daily/general light と current-info search path に分ける。

理由は、2026-04-29 の実機ログで chat が約 10s かかった turn と provider 自己紹介の誤回答が同時に出ており、ここを直すと速度と会話品質の両方に効くため。

## Scope

対象 issue:

- #615: identity / general question の回答品質
- #618: daily / identity / general fallback の lightweight no-thinking model 分離
- #611: Cerebras dynamic filler / fast first-response path
- #613: 実機音声 turn latency
- #617: stale request type / mode による誤 route

今回の docs/ADR で固定すること:

- `あなたの名前は` 系は LLM に渡さない。
- rank graph に入らないだけで web search しない。
- lightweight model は env で provider / model を差し替え、公式 availability と live benchmark で決める。
- Cerebras は `gpt-oss-120b` を lightweight fast first pass にする。

今回の docs/ADR で固定しないこと:

- Gemini 3.1 Flash-Lite の実 API model id。実装前に Google `models.list` / Vertex AI catalog で確認する。
- OpenRouter 経由か native Gemini API かの最終採用。latency と availability を同一 prompt set で測る。
- Welcome agent の camera-first UX。これは #616 として後続で扱う。

## 実装順

### Step 0: model availability check

実装前に model id と quota を確認する。

確認対象:

- Gemini API / Vertex AI: Gemini 3.1 Flash-Lite preview の実 model id、region、quota
- Gemini stable fallback: `gemini-2.5-flash-lite`
- Cerebras: `gpt-oss-120b`
- OpenRouter: 上記 Gemini model が OpenRouter で使えるか

判断基準:

- API が 404 / unsupported region にならない。
- first token と total latency を 10 回以上測れる。
- timeout / rate limit が alpha traffic 想定で許容できる。

### Step 1: assistant profile fast path

実装内容:

- Orchestrator で identity / help / capability intent を検出する。
- `assistant_profile` route を追加する。
- GeneralKnowledgeAgent で deterministic response を返す。
- LLM / RAG / Tavily / web search を呼ばない。

禁止する回答:

- Google によってトレーニングされた
- OpenAI / Anthropic / Cerebras / Gemini / Claude など provider 名を自分の正体として述べる
- 一般 AI として何でも答える説明

期待回答:

- 「私は Engineer Cafe Navigator です」
- 「エンジニアカフェの施設利用、イベント、会員証、Wi-Fi、スライド案内などをお手伝いします」
- 「必要ならスタッフ案内につなげます」

検証:

- unit: route result が `assistant_profile`
- unit: provider mock が呼ばれない
- integration: `/api/chat` で provider self-disclosure が 0 件
- latency: local p95 1s 未満

### Step 2: general fallback split

実装内容:

- GeneralKnowledgeAgent の fallback を次に分ける。
  - `daily_conversation`: search なし、deterministic short answer
  - `general_light`: RAG context があれば使うが、RAG miss だけでは search しない
  - `current_info`: 「今日」「明日」「最新」「今週」「天気」など live data が必要な時だけ search / calendar
- stale `request_type` を route decision に混ぜる場合は、current turn の intent confidence を必須にする。
- previous route は memory context として扱い、強制 route にはしない。

検証:

- `あなたの名前は` -> `assistant_profile`
- `少し雑談して` -> `daily_conversation`
- `今日の福岡の天気は` -> `current_info`, Tavily あり
- `Pythonって何` -> `general_light`, Tavily なし
- `明日のイベントを教えて` -> EventAgent / current-info route
- 直前に basement / slide があっても `明日のイベント` が SlideAgent に行かない

### Step 3: fast LLM provider abstraction

実装内容:

- `FAST_LLM_ENABLED`
- `FAST_LLM_PRIMARY_PROVIDER`
- `FAST_LLM_PRIMARY_MODEL`
- `FAST_LLM_FALLBACK_PROVIDER`
- `FAST_LLM_FALLBACK_MODEL`
- `FAST_LLM_TERTIARY_PROVIDER`
- `CEREBRAS_ENABLED`
- `CEREBRAS_API_KEY`
- `CEREBRAS_FAST_MODEL`
- `CEREBRAS_REASONING_EFFORT`

最小実装:

- 既存 OpenRouter provider を壊さず、fast model resolver を追加する。
- `FAST_LLM_PRIMARY_PROVIDER=cerebras` のときは Cerebras をOpenRouterより先に試す。
- Cerebras が失敗した場合は OpenRouter Gemini primary/fallback に戻す。
- Cerebras は OpenAI-compatible Chat Completions として provider を追加する。
- `gpt-oss-120b` の場合は `reasoning_effort=low` を送れるようにする。

検証:

- env 未設定では現行動作を維持する。
- env 設定時だけ fast provider を使う。
- provider failure では fallback model に落ちる。

### Step 4: benchmark gate

prompt set:

- identity: `あなたの名前は`
- help: `何ができますか`
- daily: `少し雑談して`
- daily-weather: `今日の福岡の天気は`
- general: `Pythonって何`
- current-info: `明日のイベントを教えて`
- stale-context: `地下について教えて` の後に `明日のイベントを教えて`

記録する値:

- provider
- model
- route
- first token latency
- total latency
- web search used
- RAG used
- TTS text length
- provider self-disclosure violation

合格基準:

- identity p95 < 1s
- daily/general light p95 < 3s
- identity provider self-disclosure 0 件
- non-current general で Tavily 0 件
- stale route regression 0 件

## env 配置

ローカルでは secret を chat に貼らず、backend app が確実に読む `backend/.env` に置く。
`.env.local` はテストや補助 loader が明示的に読む場合だけ使う。

```env
FAST_LLM_ENABLED=true
FAST_LLM_PRIMARY_PROVIDER=cerebras
FAST_LLM_PRIMARY_MODEL=google/gemini-3.1-flash-lite-preview
FAST_LLM_FALLBACK_PROVIDER=gemini
FAST_LLM_FALLBACK_MODEL=google/gemini-2.5-flash-lite
FAST_LLM_TERTIARY_PROVIDER=cerebras
CEREBRAS_ENABLED=true
CEREBRAS_API_KEY=your-cerebras-key
CEREBRAS_FAST_MODEL=gpt-oss-120b
CEREBRAS_REASONING_EFFORT=low
```

GitHub Actions:

```bash
gh secret set CEREBRAS_API_KEY --body "$CEREBRAS_API_KEY"
```

Google Secret Manager:

```bash
gcloud secrets create CEREBRAS_API_KEY --replication-policy=automatic
printf "%s" "$CEREBRAS_API_KEY" | \
  gcloud secrets versions add CEREBRAS_API_KEY --data-file=-
```

既に secret がある場合は `gcloud secrets create` は不要。

Cloud Run deploy では `--update-secrets` に `CEREBRAS_API_KEY=CEREBRAS_API_KEY:latest` を追加する。

## リリース判定

「絶対に動く保証」は外部 API を使う以上、静的な約束ではなく release gate と rollback 条件で作る。

alpha GO 条件:

- ADR 018 の deterministic fast path が実装済み
- benchmark gate が green
- Cloud Run live logs で #613 の遅延分解が更新済み
- #615 / #618 に実測値と model choice の理由がコメント済み
- #611 は採用範囲、または延期理由が明記済み

alpha NO-GO 条件:

- identity が provider 自己紹介を 1 回でも返す
- daily/general light が web search に落ちる
- voice turn p95 が改善せず、どの区間が遅いかログで説明できない
- Gemini / Cerebras の model id が公式 API で確認できないまま hardcode されている

## 参照

- [ADR 018](../adr/018-alpha-fast-response-and-assistant-profile-routing.md)
- [STATUS.md](../STATUS.md)
- [DEPLOYMENT.md](../DEPLOYMENT.md)

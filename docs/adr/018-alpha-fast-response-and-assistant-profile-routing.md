# ADR 018: Alpha Fast Response And Assistant Profile Routing

## ステータス

採用

## 日付

2026-04-30

## 背景

2026-04-29 の実機確認で、alpha release を止めるべき UX / correctness regression が確認された。

- `あなたの名前は` という一般的な identity 質問で、provider 自己紹介に寄った回答が返った。
- rank graph / intent routing に入らない質問が GeneralKnowledgeAgent に落ち、RAG miss 時に web search と大きい LLM 応答へ進む。
- 実測ログでは、1 turn が STT 約 3s、chat 約 10s、TTS 約 4s の合計約 17s に達したケースがある。
- 別ケースでは STT が約 14s、chat が約 2s、TTS が約 2.4s で、直前 request type が残り SlideAgent に誤誘導された。

alpha で許容できないのは「モデルが遅いこと」だけではない。identity / help / 日常会話のような kiosk 上の基本質問まで RAG + web search + heavyweight LLM に流す設計が、遅延と回答品質の両方を悪化させている。

## 公式モデル情報の扱い

モデル仕様はリリースと deprecation が早いため、実装では日付付きの公式情報と実測を分離する。

2026-04-30 時点の参照元:

- Google DeepMind: Gemini 3.1 Flash-Lite は Preview、Gemini API / Google AI Studio / Vertex AI で提供される。
- Google DeepMind model card: Gemini 3.1 Flash-Lite の output speed は 363 tok/s、Gemini 2.5 Flash-Lite Dynamic は 366 tok/s とされる。
- Google Cloud Vertex AI model lifecycle: stable model としては `gemini-2.5-flash-lite` が listing され、retirement date は 2026-07-22。
- Cerebras supported models: production model として `gpt-oss-120b` は約 3000 tok/s、`llama3.1-8b` は約 2200 tok/s。
- Cerebras deprecation: `qwen-3-32b` と `llama-3.3-70b` は 2026-02-16 に deprecated。移行先として GPT OSS 120B が推奨されている。
- Cerebras reasoning: `gpt-oss-120b` は `reasoning_effort` を `low` / `medium` / `high` で制御でき、`low` は最小 reasoning で高速化に寄せる。
- OpenAI models: 複雑な推論には `gpt-5.5`、latency / cost 最適化には `gpt-5.4-mini` / `gpt-5.4-nano` が公式に推奨されている。

これにより、次のルールを採用する。

- Gemini 3.1 Flash-Lite は候補に入れるが、API model id は deploy 前に Google の `models.list` / Vertex AI catalog で確認する。
- Gemini 2.5 Flash-Lite は stable fallback として保持する。
- Cerebras の alpha production 候補は `gpt-oss-120b` を第一候補にする。`llama3.1-8b` は速度は速いが、短期 deprecation / capability risk があるため default にしない。
- GPT-5.4 Nano は valid な高速候補だが、Engineer Cafe Navigator の会話 default fallback にはしない。Gemini 系で primary/fallback を揃え、OpenAI は evaluation / vision / explicit fallback 候補に限定する。
- OpenRouter 経由の model id と native provider の model id は別物として扱い、env で差し替え可能にする。

## 決定

### 1. Identity / help / capability はモデルを呼ばない

次の質問群は LLM / RAG / web search に渡さず、canonical response を返す。

- 名前: `あなたの名前は`, `what is your name`
- 正体: `あなたは誰`, `who are you`
- できること: `何ができますか`, `what can you do`
- 役割: `案内して`, `どう使うの`, `help`

回答は Engineer Cafe Navigator の役割だけを述べる。Google / OpenAI / Anthropic / Cerebras など provider 自己紹介は禁止する。

### 2. General fallback は fast path と search path に分ける

GeneralKnowledgeAgent は一律に RAG miss -> web search -> LLM へ進ませない。

- `assistant_profile`: deterministic response
- `daily_conversation`: deterministic short response first、search なし
- `general_light`: fast LLM、RAG context があれば使う、search なし
- `current_info`: 天気・ニュース・今日/明日など current external facts が必要なときだけ search path
- `memory`: memory helper のみを使い、施設案内や slide route に転送しない

### 3. Fast LLM は env で provider / model を差し替える

default candidate は固定せず、release 前 benchmark で決める。

推奨 env:

```env
FAST_LLM_PRIMARY_PROVIDER=cerebras
FAST_LLM_PRIMARY_MODEL=google/gemini-3.1-flash-lite-preview
FAST_LLM_FALLBACK_PROVIDER=gemini
FAST_LLM_FALLBACK_MODEL=google/gemini-2.5-flash-lite
FAST_LLM_TERTIARY_PROVIDER=cerebras
CEREBRAS_ENABLED=true
CEREBRAS_API_KEY=
CEREBRAS_FAST_MODEL=gpt-oss-120b
CEREBRAS_REASONING_EFFORT=low
```

`FAST_LLM_PRIMARY_PROVIDER=cerebras` の場合、`CEREBRAS_FAST_MODEL` を native Cerebras Chat Completions に投げる。Cerebras が失敗した場合は `FAST_LLM_PRIMARY_MODEL` / `FAST_LLM_FALLBACK_MODEL` を OpenRouter 経由の Gemini fallback として使う。

### 4. Cerebras は lightweight fast first pass にする

Cerebras は `gpt-oss-120b` の throughput が非常に高いため、軽量回答では OpenRouter より先に native API を試す。

- first response / filler の短文生成
- daily conversation の fallback
- short answer rewrite

RAG grounded answer や施設情報の authoritative answer は、出典・文脈の取り扱いを確認するまで既存 route の品質 gate を通す。Cerebras primary が失敗した場合は OpenRouter Gemini fallback に戻し、alpha の可用性を維持する。

### 5. Alpha release gate は「平均」ではなく p95 と禁止語で見る

alpha release 前に最低限通す gate:

| Gate | 目標 |
| --- | --- |
| identity response | p95 1s 未満、LLM / RAG / web search 不使用 |
| daily/general light chat | daily は p95 1s 未満、general light は p95 3s 未満、Tavily 不使用 |
| current-info route | 天気など受付雑談の live facts だけ web search / calendar を使う |
| provider self-disclosure | Google / OpenAI / Anthropic / Cerebras 等の自己紹介を 0 件にする |
| stale request type | 前 turn の `request_type` で別 route に流れない |
| full voice turn | STT + chat + TTS p95 を issue #613 の基準で再計測 |

## 採用理由

identity / help は kiosk の基本機能であり、生成 AI の自由回答に任せる必要がない。ここを deterministic にすれば、最重要の品質問題と 10s 級 chat latency を同時に潰せる。

fast LLM は model churn が激しい。`gemini-3.1-flash-lite-preview` のような preview model は魅力的だが、API id、region availability、quota、OpenRouter 収載状況が変わる。実装を特定 model に密結合せず、公式 availability check と live benchmark を release gate にする。

Cerebras は速度面で有力だが、reasoning default や model deprecation を無視すると逆に alpha の再現性を壊す。`gpt-oss-120b` + `reasoning_effort=low` を短文 fast path に限定して導入する。

## 代替案

### すべて Gemini 2.5 Flash-Lite に一括変更する

実装は簡単だが、identity 質問が RAG / web search に落ちる構造は残る。速度と回答品質の根本原因を分離できないため不採用。

### すべて Cerebras に寄せる

短文速度は期待できるが、施設 RAG / web search / multilingual QA の既存品質 gate を再検証する必要がある。alpha 直前に全面移行するには blast radius が大きいため不採用。

### Frontend TTS だけを先に直す

TTS 2-4s は改善対象だが、今回の最大値は chat 10s と STT 14s も含む。identity の誤回答は TTS 改善では直らないため、優先順位は下げる。

## 実装影響

- `backend/agents/orchestrator_agent.py`: identity / help / capability intent の fast routing
- `backend/agents/general_knowledge_agent.py`: assistant profile deterministic response と fast/search path 分離
- `backend/llm/*`: provider / model を env で解決できるようにする
- `.github/workflows/ci.yml`: `CEREBRAS_API_KEY` と fast model env を Cloud Run deploy に渡す
- `backend/.env.example`: fast LLM / Cerebras env を明記
- tests: provider self-disclosure 禁止、identity p95、web search 不使用、stale request type regression

## ロールバック

fast path は env flag と route condition で無効化できる構成にする。

- `ASSISTANT_PROFILE_FAST_PATH=false`: deterministic identity route を停止
- `FAST_LLM_ENABLED=false`: daily/general light を既存 `qa_response` route に戻す
- `CEREBRAS_ENABLED=false`: Cerebras fallback / filler を停止

ただし provider self-disclosure 禁止は rollback しない。alpha の会話品質要件として常に維持する。

## 検証方針

1. unit: identity / help / capability route が LLM provider を呼ばないこと
2. unit: GeneralKnowledgeAgent が RAG miss だけで Tavily を呼ばないこと
3. integration: `/api/chat` で `あなたの名前は` が 1s 未満かつ provider 名を含まないこと
4. integration: `明日のイベントを教えて` が stale slide / basement request type に引きずられないこと
5. benchmark: Gemini 3.1 Flash-Lite, Gemini 2.5 Flash-Lite, Cerebras `gpt-oss-120b` を同一 prompt set で p50 / p95 比較すること
6. live: Cloud Run logs の `chat_response.latency_ms`, `stt_overall_duration_ms`, TTS duration を issue #613 に追記すること

## 2026-05-02 検証結果

`alpha-live-verification` full run `25244933308` で、Cerebras fast path は live log 上で
`gpt-oss-120b` を使っていることを確認した。ただし alpha GO はまだ不可。

この時点で残っていた優先課題:

- #658: STT preflight latency
- #660: H-UI Welcome OCR overlay
- #659: B routing `B1-BIZ-002`
- #653 / #672: Q/C answer quality
- #662: Supabase UUID/log hygiene

また、RAGAS は fast response の product path ではなく evaluation path だが、alpha gate の信頼性に直結する。
2026-05-02 に GitHub Actions `OPENAI_API_KEY` を更新し、run `25247945549` で direct OpenAI
`gpt-5.2-2025-12-11` が使われることを確認した。OpenRouter fallback は GO 証跡として使わない。

## 2026-05-03 検証結果

PR #674, #675, #676 を develop に merge し、Cloud Run staging に `d789a2cd899779423947c40a3d65e19382f52d30`
を deploy した。

検証済み:

- Cloud Run revision: `engineer-cafe-backend-00148-82c`
- Targeted B run: `25254789937`
- B routing / slide result: `64 passed, 0 warned, 0 failed`
- `B1-BIZ-003` (`土日祝日も利用できますか。`): `business_info`, `1258ms`
- slide narration B5-1..B5-5: PASS
- Cloud Logging UUID / reception persistence errors during the B run window: 0 rows

この結果により、ADR 018 の「identity / business-info / slide route は unnecessary heavyweight fallback
に流さない」という方針のうち、B routing と slide smoke の live proof は成立した。

一方、voice turn 全体の alpha GO はまだ不可。STT-only current-revision gate では p50 `5180ms`,
p95/max `29217ms`, over-10s ratio `14.3%` が残っている。したがって、次の実装優先度は
fast LLM / routing ではなく #658 の STT long-tail mitigation とする。

ADR 018 の release gate を以下に更新する。

- identity / assistant profile: deterministic response, provider self-disclosure 0 件を維持
- business-info fast routing: B targeted suite green を維持
- slide narration: B5 smoke green を維持
- Cloud Run log hygiene: synthetic session ID による UUID 400 を 0 件に維持
- full voice turn: STT p95 が current-revision gate を満たすまで alpha GO 不可

## 参照

- https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/
- https://deepmind.google/models/model-cards/gemini-3-1-flash-lite/
- https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions
- https://inference-docs.cerebras.ai/models/overview
- https://inference-docs.cerebras.ai/capabilities/reasoning
- https://inference-docs.cerebras.ai/support/deprecation
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/models/gpt-5.4-nano/

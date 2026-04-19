# ADR-008: 運用検証とデプロイ・ガードレール

## ステータス

Accepted (2026-04-19)

## 背景

2026-04-19 時点で、3 月の hardening audit で挙がっていた項目の一部はすでにコード上で解消されていました。

- frontend middleware があり、admin / cron / monitoring route を保護している
- `API_SECRET_KEY` 未設定時の backend production startup は fail-closed
- reception session state は repository layer 経由で永続化されている
- voice / character の feature-discovery endpoint は実装済み

しかし live audit では、コードレビューだけでは見えない production risk が残っていることも確認されました。

1. 2026-04-16 から 2026-04-19 UTC の Cloud Run ログで `POST /api/character` の `403` が繰り返し出ていた
2. 一方で、最新 production frontend route は後から `200` を返しており、恒常故障ではなく release drift を示唆していた
3. Cloud Run ログでは `/api/voice` を中心に 60 秒超の slow request も出ていた
4. いくつかの文書は、すでに解消した blocker を open のまま記述していた

このため、「何を production truth とみなすか」「release をどう検証するか」を ADR として固定する必要があります。

## 決定

この repository では、以下を運用ルールとします。

### 1. Production truth は code + live verification で決める

architecture / security / operations に関する主張は、次の裏取りがない限り current とみなしません。

- 現在の repository code
- 現在の deployment configuration
- runtime-sensitive な論点については live operational evidence

### 2. Frontend-authenticated smoke check を release validation に含める

production release では、direct backend health だけでなく、実際の Vercel -> Cloud Run 経路を検証する必要があります。

最低限の確認項目:

- production frontend 経由の `GET /api/voice?action=supported_languages` が `200`
- production frontend 経由の `POST /api/character` が `200`

### 3. `BACKEND_API_KEY` と `API_SECRET_KEY` は coupled contract とみなす

frontend server runtime と backend runtime は、以下の 2 つで 1 つの運用上の認証境界を構成します。

- Vercel `BACKEND_API_KEY`
- Cloud Run `API_SECRET_KEY`

片方だけ変更して release check を省略することは deployment risk として扱います。

### 4. Live latency は test concern ではなく release concern とみなす

local / CI の test があるだけでは load / latency work は完了とみなしません。production-ready と呼ぶには、
live log review と documented baseline が必要です。

### 5. 過去の plan document には superseded を明示する

過去の運用文書を repo に残すこと自体は許容します。ただし、新しい plan や status が action list を置き換えた場合は、
それを明示しなければなりません。

## 影響

### Positive

- stale documentation が current blocker を誤って広げることを防げる
- deploy validation が実際の frontend -> backend auth chain を通るようになる
- runtime regression を早く見つけられる
- 「実装済み」と「まだ runtime で残る課題」の切り分けがしやすくなる

### Negative

- release procedure は少し重くなる
- operator は smoke script と log review を維持する必要がある
- document 更新時に過去計画との supersession 管理が必要になる

## フォローアップ

- Issue `#468`: deploy smoke gate による auth drift 防止
- Issue `#140`: latency / load baseline
- `docs/STATUS.md`, `docs/SECURITY.md`, `docs/DEPLOYMENT.md` を 2026-04-19 時点に更新

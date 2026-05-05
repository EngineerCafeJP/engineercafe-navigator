# セキュリティドキュメント

> **索引**: [Documentation hub（README.md）](README.md) · [STATUS.md](STATUS.md)
>
> Last updated: 2026-05-05（運用数値・ゲートの正本は [STATUS.md](STATUS.md)）。現在の production 構成（Vercel frontend / Cloud Run backend / Supabase）に合わせています。

## 概要

Engineer Cafe Navigator の現行セキュリティモデルは、主に次の 3 層で成立しています。

1. frontend の operator-only route 保護
2. Vercel から Cloud Run への server-side API key 認証
3. Supabase service role を server-side のみに閉じること

いま一番大きいリスクは「認証なしの route が丸見え」ではありません。実際には、
frontend `BACKEND_API_KEY` と backend `API_SECRET_KEY` の deploy-time drift により、
protected route が一時的に `403` を返すことです。

## 認証アーキテクチャ

### レイヤー 1: フロントエンド Middleware

**対象ファイル**: `frontend/src/middleware.ts`

`/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` は Next.js Edge Runtime middleware で保護されています。

動作:

1. `ADMIN_API_SECRET` を読む
2. `NODE_ENV=production` で secret がなければ即 `401`
3. secret がある場合は `Authorization: Bearer <ADMIN_API_SECRET>` を timing-safe に比較
4. 不一致なら `401`

保護対象:

| パターン | 用途 |
|---|---|
| `/api/admin/:path*` | Knowledge base 管理、STT vocabulary、admin 操作 |
| `/api/cron/:path*` | 定期 import や運用ジョブ |
| `/api/monitoring/:path*` | internal health / metrics |

除外:

- `/api/alerts/webhook` は middleware の対象外
- こちらは `ALERT_WEBHOOK_SECRET` で独立保護

### レイヤー 2: Frontend → Backend の API キー

**対象ファイル**:

- `frontend/src/lib/api/backend-proxy.ts`
- `backend/main.py`

frontend proxy は Vercel server runtime の `BACKEND_API_KEY` を読み、backend への request に
`X-API-Key` として付与します。

backend は `API_SECRET_KEY` と `hmac.compare_digest` で照合します。

重要な運用事実:

- Cloud Run は `API_SECRET_KEY` がなければ production で起動失敗する
- Vercel は `BACKEND_API_KEY` が stale / missing でも startup 自体は止まらない

つまり backend 単体では fail-closed ですが、end-to-end の release は smoke check をしないと壊れたまま通る可能性があります。

### レイヤー 3: Backend 起動ゲート

`backend/main.py` は次を保証します。

- `ENVIRONMENT=production` かつ `API_SECRET_KEY` 未設定なら起動失敗
- protected route に invalid / missing `X-API-Key` で来た request は `403`

### 防御の深さ（要約）

| シナリオ | FE middleware | FE プロキシ鍵 | BE 依存 | 結果 |
|---|---|---|---|---|
| 有効な Bearer、`BACKEND_API_KEY`、`API_SECRET_KEY` が揃う | 通過 | 通過 | 通過 | 処理される |
| 有効な Bearer だが `BACKEND_API_KEY` が欠落／古い | 通過 | 失敗 | 403 | BE で拒否 |
| Bearer が無効 | 401 | — | — | Edge で拒否 |
| production で `ADMIN_API_SECRET` 欠落 | 401 | — | — | Edge で拒否 |
| production で `API_SECRET_KEY` 欠落 | — | — | 起動失敗 | プロセスが立ち上がらない |

## サーバー側のデータアクセス

Supabase service-role access は引き続き server-side に限定されています。

- Next.js route handlers
- FastAPI backend services

主な table:

| テーブル | アクセス経路 |
|---|---|
| `knowledge_base` | backend または authenticated frontend admin proxy |
| `reception_sessions` | backend repository |
| `conversation_sessions` | backend |
| `conversation_history` | backend |
| `agent_memory` | backend |

## レート制限

FastAPI backend は `slowapi` を使用します。

これはもう soft optional import ではありません。

- production 相当環境で `slowapi` がなければ起動失敗
- Cloud Run / Vercel の platform limit も補助的に効く

## 入力検証

### Frontend

- route handler では必要に応じて Zod を使用
- 通常の admin 操作で browser が backend URL を直接持つ必要はない

### Backend

- FastAPI request model は Pydantic で検証
- `backend/utils/input_sanitizer.py` に prompt-bound input の追加 sanitization がある

## 環境変数契約

production deploy に関わる主要変数:

| 変数名 | サービス | 起動ブロック | 目的 |
|---|---|---|---|
| `ADMIN_API_SECRET` | Frontend (Vercel) | Yes, middleware behavior | `/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` を保護 |
| `BACKEND_API_KEY` | Frontend (Vercel server runtime) | No | protected backend route に `X-API-Key` を付ける |
| `API_SECRET_KEY` | Backend (Cloud Run) | Yes (`sys.exit(1)`) | frontend -> backend request を検証 |
| `ALERT_WEBHOOK_SECRET` | Frontend (Vercel) | No | `/api/alerts/webhook` POST を保護 |
| `SUPABASE_SERVICE_ROLE_KEY` | Frontend + Backend | No, but functionally required | server-side Supabase access |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | Backend | No, but functionally required | model / embedding provider |

運用ルール:

- `BACKEND_API_KEY` と `API_SECRET_KEY` は 1 つの coupled contract として扱う
- 片方だけを更新して smoke check を省略するのは release risk

## 現在の残課題

### Deploy-time auth drift はまだ起こり得る

2026-04-16 から 2026-04-19 UTC の Cloud Run ログで `POST /api/character` の `403` がまとまって出ている一方、
最新 production frontend probe は後で `200` を返しています。

解釈:

- route protection 自体は機能している
- release validation が足りない

関連 Issue:

- `#468`

### Admin / backoffice E2E coverage は kiosk より薄い

kiosk 側の smoke coverage の方が強く、operator-only surface の E2E はまだ薄いです。

### Supabase runtime observability は通常の security checklist に入っていない

この audit では linked project は確認できましたが、data layer の recent runtime log を同じ密度では追えていません。

## セキュリティテスト

### マージ前チェック

- `ruff check .`
- `black --check .`
- `pnpm lint`
- `pnpm typecheck`
- 既存 backend / frontend test suite

### 本番リリース前の手動確認

- `ADMIN_API_SECRET`, `BACKEND_API_KEY`, `API_SECRET_KEY` が target 環境にあることを確認
- `/api/admin/knowledge` に `Authorization` なしで投げて `401` を確認
- backend に `X-API-Key` なしで投げて `403` を確認
- frontend-authenticated smoke check として次を確認
  - `GET /api/voice?action=supported_languages`
  - `POST /api/character`
- deploy 直後の Cloud Run ログに `403` / `5xx` スパイクがないことを確認

## インシデント対応

| 深刻度 | 説明 | 目標対応時間 |
|---|---|---|
| Critical | 認証バイパス、広範な障害、データ流出 | 30 分 |
| High | 403 のデプロイ不整合の反復、秘密鍵ローテーション、重大な機能低下 | 2 時間 |
| Medium | 疑わしいアクセス、レート制限超過、依存 CVE | 24 時間 |
| Low | 情報レベルの指摘、低リスクな依存の問題 | 1 週間 |

credential 漏えい時:

- 該当 secret を即 rotate
- rotate 後に frontend-authenticated smoke check を再実行
- 該当時間帯の Cloud Run ログを確認

## 参照

- [DEPLOYMENT.md](DEPLOYMENT.md)
- [STATUS.md](STATUS.md)
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md)
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md)

[Home](../README.md) | [API 説明（日本語）](api/API-ja.md) | [Deployment](DEPLOYMENT.md) | [Status](STATUS.md)

# API ドキュメント - Engineer Cafe Navigator

[English](./API.md) | 日本語版

現在の Vercel + Cloud Run 構成に合わせて更新した API リファレンスです。

## 概要

Engineer Cafe Navigator は 2 層構成の API を採用しています。

- 公開クライアントは通常 `<frontend-production-origin>/api` 配下のフロントエンド route を呼び出します。ここでいう origin は `docs/DEPLOYMENT.md` に記載した Vercel の Production domain です。
- フロントエンドの `/api/*` route は FastAPI バックエンドへプロキシし、`BACKEND_API_KEY` を使って `X-API-Key` を自動付与します。
- `/api/admin/*`、`/api/cron/*`、`/api/monitoring/*` はフロントエンド側で `Authorization: Bearer <ADMIN_API_SECRET>` により保護されます。
- `/api/chat` などのコアなバックエンド route は、通常ブラウザから直接呼び出す想定ではありません。

## ベース URL

```text
フロントエンド本番: <frontend-production-origin>/api
フロントエンド local: http://localhost:3000/api
バックエンド local:   http://localhost:8000
```

## 認証

| 対象 | 認証 |
| --- | --- |
| 公開フロントエンド proxy route | クライアント側シークレット不要 |
| バックエンド直接呼び出し | `X-API-Key: <API_SECRET_KEY>` |
| フロントエンドの admin / cron / monitoring | `Authorization: Bearer <ADMIN_API_SECRET>` |

補足:

- `BACKEND_API_KEY` は Next.js フロントエンドがバックエンドへプロキシするためのサーバー側シークレットです。
- `ADMIN_API_SECRET` はフロントエンド middleware により `/api/admin/*`、`/api/cron/*`、`/api/monitoring/*` に適用されます。
- バックエンドの CORS は設定された Vercel Production origin と local 開発 origin を許可しています。

## アーキテクチャ補足

フロントエンドの `/api/*` route は、そのままバックエンドそのものではありません。

- `/api/voice`、`/api/qa`、`/api/slides`、`/api/character`、`/api/ocr`、`/api/reception/*` はバックエンド route への proxy です。
- 受付スライド表示は `frontend/public/reception` の静的 PDF と、`frontend/public/reception/audio` の事前生成済みページ別音声を使います。
- `/api/admin/*` は edge 保護されたフロントエンド admin route です。バックエンドへ proxy するものと、フロントエンド側の admin utility を使うものがあります。

## フロントエンド API

### POST /api/voice

バックエンド `POST /api/voice` への proxy です。

代表的なリクエスト:

```json
{
  "action": "speech_to_text",
  "audioData": "base64-encoded-audio",
  "sessionId": "session-123",
  "language": "ja"
}
```

現在のバックエンドでサポートされる action:

- `speech_to_text`
- `text_to_speech`
- `set_language`
- `interrupt`

代表的なレスポンス:

```json
{
  "success": true,
  "transcript": "エンジニアカフェについて教えてください",
  "audioResponse": "base64-audio",
  "emotion": "neutral",
  "sessionId": "session-123"
}
```

### GET /api/backgrounds

フロントエンドの背景 manifest から画像ファイル名一覧を返します。

レスポンス例:

```json
{
  "images": ["IMG_5573.JPG", "placeholder.svg"],
  "total": 2
}
```

### POST /api/slides

バックエンド `POST /api/slides` への proxy です。

この route は SlideAgent のナレーションとスライド内質問のための endpoint です。キオスクのスライド表示 UI は静的 PDF ガイドを使います。

現在のバックエンドでサポートされる action:

- `narrate`
- `narrate_current` (`narrate` の alias)
- `next`
- `previous`
- `goto`
- `question`
- `answer_question` (`question` の alias)

リクエスト例:

```json
{
  "action": "next",
  "slideNumber": 2,
  "language": "ja",
  "sessionId": "session-123"
}
```

レスポンス例:

```json
{
  "success": true,
  "answer": "次のスライドでは施設をご案内します。",
  "emotion": "neutral",
  "slideNumber": 3,
  "metadata": {
    "language": "ja"
  }
}
```

### POST /api/qa

バックエンド `POST /api/chat` への proxy です。

重要な点:

- フロントエンドは `question` または `text` を受け取ります。
- バックエンドにはそれを `query` として転送します。
- 旧説明にある `ask_question` は現行の実装説明としては不正確です。実際に呼ばれるのは `/api/chat` です。

リクエスト例:

```json
{
  "question": "営業時間を教えてください",
  "sessionId": "session-123",
  "language": "ja",
  "visitorId": "visitor-123"
}
```

バックエンドへ転送される payload:

```json
{
  "query": "営業時間を教えてください",
  "session_id": "session-123",
  "language": "ja",
  "visitor_id": "visitor-123"
}
```

レスポンス例:

```json
{
  "success": true,
  "answer": "Engineer Cafe は公開されている営業時間内に利用できます。",
  "emotion": "neutral",
  "metadata": {
    "session_id": "session-123"
  }
}
```

`GET /api/qa` はフロントエンド補助 action を持ちます。

- `action=question_categories`
- `action=sample_questions&language=ja|en`
- `action=health`

### POST /api/ocr

バックエンド `POST /api/chat` への proxy です（画像データ付き）。

画像と任意のクエリを受け取り、`image_data` 付きでバックエンドの chat endpoint に転送して OCR/ビジョン処理を行います。

リクエスト例:

```json
{
  "image_data": "base64-encoded-image",
  "query": "この画像を分析してください",
  "session_id": "session-123",
  "language": "ja"
}
```

レスポンス例:

```json
{
  "success": true,
  "answer": "この画像には名刺が写っており...",
  "emotion": "neutral",
  "metadata": {
    "session_id": "session-123"
  }
}
```

補足: フロントエンドは `image_data` の存在を検証してから proxy します。バックエンドはビジョン機能を持つ既存の chat パイプラインで画像を処理します。

### POST /api/character

バックエンド `POST /api/character` への proxy です。

リクエスト例:

```json
{
  "action": "setExpression",
  "emotion": "happy",
  "animation": "greeting"
}
```

レスポンス例:

```json
{
  "success": true,
  "message": "{\"emotion\":\"happy\"}"
}
```

`GET /api/character` は現在シンプルなフロントエンド status payload を返します。

```json
{
  "status": "ok"
}
```

## バックエンド API

以下はフロントエンド proxy の背後にある主要な FastAPI route です。

### POST /api/chat

LangGraph ベースのメイン chat endpoint です。

- `X-API-Key` 必須
- request body は `query`、`session_id`、`language`、任意の `context`、任意の `visitor_id`
- `answer`、`emotion`、`metadata`、任意の `vrm_control` を返します

リクエスト例:

```http
POST /api/chat
X-API-Key: your-api-secret
Content-Type: application/json
```

```json
{
  "query": "Tell me about Engineer Cafe",
  "session_id": "session-123",
  "language": "en"
}
```

### POST /api/chat/stream

SSE 版の chat endpoint です。

- `X-API-Key` 必須
- request schema は `/api/chat` と同じ
- `text/event-stream` を返します

### POST /api/agent/invoke

LangGraph を直接実行する endpoint です。

- `X-API-Key` 必須
- request schema は `/api/chat` と同じ
- `{ "status": "success", "result": ... }` を返します

### POST /api/interrupt

進行中 session の割り込み endpoint です。

- `X-API-Key` 必須
- request body:

```json
{
  "session_id": "session-123"
}
```

### GET /health

バックエンドの health endpoint です。

- バックエンド service と依存先の health 情報を返します
- 運用上の health check に使います
- 現行実装では `/api/chat` と同じ `X-API-Key` 依存は付いていません

レスポンス例:

```json
{
  "status": "ok",
  "service": "engineer-cafe-navigator-backend",
  "checks": {
    "api": "ok",
    "supabase": "ok",
    "llm_provider": "configured"
  }
}
```

## Admin API

フロントエンド admin route はすべて `/api/admin/*` 配下にあり、以下が必要です。

```http
Authorization: Bearer <ADMIN_API_SECRET>
```

### /api/admin/knowledge

サポートメソッド:

- `GET`: knowledge entry 一覧取得
- `POST`: knowledge entry 作成

現在の挙動:

- バックエンド `/api/knowledge` へ proxy します
- 一覧取得時はフロントエンドで `search` を `keyword` に正規化します

### /api/admin/knowledge/[id]

サポートメソッド:

- `GET`: 単一 knowledge entry 取得
- `PUT`: 単一 knowledge entry 更新
- `DELETE`: 単一 knowledge entry 削除

単一 entry の CRUD を提供する edge 保護されたフロントエンド admin route です。

### /api/admin/knowledge/categories

サポートメソッド:

- `GET`: category、subcategory、source、language の metadata 取得

### /api/admin/stt

サポートメソッド:

- `GET`: vocabulary 一覧、または `?id=...` で単一 item 取得
- `POST`: vocabulary 作成
- `PUT`: `?id=...` を使って vocabulary 更新
- `DELETE`: `?id=...` を使って vocabulary 削除

現在の挙動:

- バックエンド `/api/stt/vocabulary` へ proxy します
- 単一 item 操作の前に `id` 形式を検証します

## OCR API

### POST /api/ocr

バックエンド `POST /api/ocr` への proxy です。カメラ画像から来訪者を識別します。

サポートモード:

- `member_card` — 会員証バーコードまたは ID のスキャン
- `handwriting` — 手書きフォームからのテキスト抽出

リクエスト例:

```json
{
  "mode": "member_card",
  "imageData": "base64-encoded-image",
  "sessionId": "session-123"
}
```

レスポンス例:

```json
{
  "success": true,
  "visitorIdentity": {
    "memberId": "M-12345",
    "name": "Engineer Taro"
  },
  "rawText": "M-12345 Engineer Taro",
  "sessionId": "session-123"
}
```

レート制限があります。制限超過時は `429 Too Many Requests` を返します。

OCR バックエンドは `backend/api/ocr.py` に実装され、OCRAgent に処理を委譲します。

## Reception API

フロントエンド reception route はバックエンド `/api/reception/*` へ proxy します。

### POST /api/reception/start

reception session を開始します。OCR などで事前に識別済みの場合は `visitor_identity` フィールドを渡すことができます。

リクエスト例:

```json
{
  "session_id": "session-123",
  "language": "ja",
  "trigger_type": "button_press",
  "visitor_identity": {
    "memberId": "M-12345",
    "name": "Engineer Taro"
  }
}
```

`visitor_identity` は任意です。reception 開始前に身元が確定していない場合は省略してください。

### POST /api/reception/respond

reception 会話を継続します。

リクエスト例:

```json
{
  "session_id": "session-123",
  "reception_session_id": "reception-123",
  "message": "見学で来ました。"
}
```

### POST /api/reception/complete

reception を完了し、`ainvoke_from_reception()` 経由でメイン workflow を起動します。reception 中に収集した来訪者コンテキストを使ってエージェントが応答を生成します。

リクエスト例:

```json
{
  "session_id": "session-123",
  "reception_session_id": "reception-123"
}
```

### GET /api/reception/status/[id]

現在の reception 状態を返します。

任意 query parameter:

- `session_id`

レスポンス例:

```json
{
  "session_id": "session-123",
  "stage": "routing",
  "visitor_type": "new",
  "purpose": "tour"
}
```

## Monitoring と定期実行 route

### /api/monitoring/dashboard

- `GET`
- `Authorization: Bearer <ADMIN_API_SECRET>` 必須
- フロントエンド側の運用 metrics を返します

### /api/monitoring/migration-success

- `GET`
- `Authorization: Bearer <ADMIN_API_SECRET>` 必須
- migration dashboard data を返します

### /api/cron/update-knowledge-base

- `POST`
- `Authorization: Bearer <ADMIN_API_SECRET>` 必須

### /api/cron/update-slides

- `POST`
- `Authorization: Bearer <ADMIN_API_SECRET>` 必須

## Embeddings

現行の canonical な embedding 設定:

- モデル: `text-embedding-3-small`
- バックエンド embedding service 上の provider path: `openai/text-embedding-3-small`
- 次元数: `1536`

RAG、admin knowledge ingestion、backend search の説明では、OpenAI `text-embedding-3-small` の 1536 次元を正としてください。

## エラー処理

代表的なエラーレスポンス:

```json
{
  "error": "Internal server error"
}
```

バックエンドの validation / auth failure でよく使われる status:

- `400 Bad Request`
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`
- `409 Conflict`
- `422 Unprocessable Entity`
- `429 Too Many Requests`
- `500 Internal Server Error`
- `503 Service Unavailable`

## 運用メモ

- 必須フロントエンド secret: `NEXT_PUBLIC_BACKEND_API_URL`, `BACKEND_API_URL`, `BACKEND_API_KEY`, `ADMIN_API_SECRET`
- 必須バックエンド secret: `API_SECRET_KEY`
- backend health と CORS は Vercel 本番 domain を前提に設定されています
- 旧 Cloudflare 参照は履歴上の情報であり、現行運用の手順としては使用しません

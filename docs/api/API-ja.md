# API ドキュメント - Engineer Cafe Navigator

> 注意: この文書には旧 deployment 前提や更新途中の route 説明が含まれる可能性があります。現行判断は `docs/STATUS.md` と実装コードを優先してください。

> Engineer Cafe Navigator 音声AIエージェントシステムの完全なREST API仕様書

[English](./API.md) | 日本語版

## 📖 概要

Engineer Cafe Navigatorは以下のRESTful APIエンドポイントを提供します：

- **音声処理**: 音声認識、合成、AI応答生成
- **感情検出**: テキストと音声からのリアルタイム感情分析
- **スライド制御**: Marpスライドの表示とナビゲーション
- **キャラクター制御**: VRMキャラクターの表情とアニメーション
- **外部連携**: WebSocket受付システム統合
- **Q&Aシステム**: AI駆動の質問応答
- **セッション管理**: コンテキスト永続化によるマルチターン会話
- **背景制御**: 動的な背景管理

## 🔗 ベースURL

```
本番環境: https://engineer-cafe-navigator.vercel.app/api
開発環境: http://localhost:3000/api
```

## 🔐 認証

APIはGoogle CloudサービスにService Account認証を使用します。クライアントリクエストにはセッションベース認証を使用します。

### Service Account設定

1. Google Cloud ConsoleでService Accountを作成
2. ロールを付与: `roles/speech.client` および `roles/texttospeech.client`
3. JSONキーをダウンロードし `./config/service-account-key.json` に配置
4. 環境変数を設定: `GOOGLE_CLOUD_CREDENTIALS=./config/service-account-key.json`

### CRONジョブ認証

CRONジョブエンドポイントは`CRON_SECRET`環境変数と一致するBearerトークンが必要です：

```http
Authorization: Bearer your-cron-secret
```

## 🎤 音声処理 API

### POST /api/voice

音声データの処理とAI応答の生成を行います。

#### リクエスト

**ヘッダー:**
```json
{
  "Content-Type": "application/json"
}
```

**ボディ:**
```json
{
  "action": "process_voice",
  "audioData": "base64エンコードされた音声データ",
  "sessionId": "セッションID",
  "language": "ja"
}
```

**追加アクション:**
- `start_session`: 新しい会話セッションを開始
- `end_session`: 現在のセッションを終了
- `set_language`: セッション言語を変更
- `get_conversation_state`: 現在の会話状態を取得
- `clear_conversation`: 会話履歴をクリア
- `handle_interruption`: ユーザー割り込みを処理
- `detect_language`: テキストから言語を自動検出

**パラメータ:**
- `action` (文字列, 必須): 実行する操作
- `audioData` (文字列): Base64エンコードされた音声データ（WebM Opus形式推奨）
- `sessionId` (文字列): start_sessionから取得したセッションID
- `language` (文字列): 言語コード（"ja"または"en"、デフォルトは"ja"）

#### レスポンス

**成功 (200):**
```json
{
  "success": true,
  "transcript": "こんにちは、エンジニアカフェについて教えてください",
  "response": "エンジニアカフェへようこそ！私たちは...",
  "audioResponse": "base64エンコードされたMP3音声",
  "shouldUpdateCharacter": true,
  "characterAction": "greeting",
  "emotion": {
    "emotion": "explaining",
    "intensity": 0.75,
    "confidence": 0.82,
    "duration": 2500
  },
  "sessionId": "セッションID"
}
```

### セッション管理の例

**セッション開始:**
```json
// リクエスト
{
  "action": "start_session",
  "visitorId": "visitor-123",
  "language": "ja"
}

// レスポンス
{
  "success": true,
  "sessionId": "5caaff9e-bae9-4131-bf49-01c6694a3e9c"
}
```

**言語切り替え:**
```json
// リクエスト
{
  "action": "set_language",
  "language": "en",
  "sessionId": "セッションID"
}

// レスポンス
{
  "success": true,
  "message": "Language updated"
}
```

**会話状態取得:**
```json
// リクエスト
{
  "action": "get_conversation_state",
  "sessionId": "セッションID"
}

// レスポンス
{
  "success": true,
  "state": "idle",
  "summary": "ユーザーはエンジニアカフェのサービスと料金について質問しました。"
}
```

### GET /api/voice

音声サービス情報の取得

#### エンドポイント

**ステータス確認:**
```http
GET /api/voice?action=status
```

**レスポンス:**
```json
{
  "success": true,
  "status": "active",
  "conversationState": "idle",
  "timestamp": "2025-05-30T06:40:49.401Z"
}
```

**サポート言語一覧:**
```http
GET /api/voice?action=supported_languages
```

**レスポンス:**
```json
{
  "success": true,
  "result": {
    "supported": ["ja", "en"],
    "current": "ja",
    "details": {
      "ja": {
        "name": "日本語",
        "englishName": "Japanese",
        "code": "ja",
        "flag": "🇯🇵",
        "voice": {
          "male": "ja-JP-Neural2-C",
          "female": "ja-JP-Neural2-B",
          "default": "ja-JP-Neural2-B"
        }
      },
      "en": {
        "name": "English",
        "englishName": "English",
        "code": "en",
        "flag": "🇺🇸",
        "voice": {
          "male": "en-US-Neural2-D",
          "female": "en-US-Neural2-F",
          "default": "en-US-Neural2-F"
        }
      }
    }
  }
}
```

## 📊 スライドAPI

### POST /api/marp

Marpマークダウンをプレゼンテーションにレンダリング

#### リクエスト
```json
{
  "action": "render_with_narration",
  "slideFile": "engineer-cafe",
  "theme": "engineer-cafe",
  "outputFormat": "both"
}
```

**パラメータ:**
- `action` (文字列, 必須): "render", "render_file", "render_with_narration"
- `slideFile` (文字列): スライドファイル名（拡張子なし）
- `theme` (文字列): テーマ名（デフォルト: "default"）
- `outputFormat` (文字列): 出力形式（"html", "json", "both"）

#### レスポンス
```json
{
  "success": true,
  "html": "<html>...</html>",
  "css": "/* テーマスタイル */",
  "slideCount": 10,
  "slideData": {
    "metadata": {
      "title": "エンジニアカフェ紹介",
      "theme": "engineer-cafe"
    },
    "slides": [
      {
        "slideNumber": 1,
        "title": "エンジニアカフェへようこそ",
        "content": "# エンジニアカフェへようこそ\n\n福岡市のイノベーション拠点"
      }
    ]
  }
}
```

### POST /api/slides

スライドナビゲーションとナレーション制御

#### リクエスト
```json
{
  "action": "next",
  "slideFile": "engineer-cafe",
  "language": "ja",
  "currentSlide": 3
}
```

**アクション:**
- `next`: 次のスライドへ
- `previous`: 前のスライドへ
- `goTo`: 指定スライドへジャンプ
- `getCurrentNarration`: 現在のナレーション取得
- `loadNarration`: ナレーションデータ読み込み

#### レスポンス
```json
{
  "success": true,
  "slideNumber": 4,
  "narration": {
    "auto": "次のスライドでは、エンジニアカフェの施設について説明します。",
    "onEnter": "エンジニアカフェには様々な施設があります。",
    "onDemand": {
      "detail": "詳しく説明しますと..."
    }
  },
  "audioUrl": "data:audio/mp3;base64,...",
  "transition": {
    "next": "施設の紹介に進みます",
    "previous": "前のスライドに戻ります"
  }
}
```

## 🤖 キャラクターAPI

### POST /api/character

3D VRMキャラクターの制御

#### リクエスト
```json
{
  "action": "update",
  "expression": "friendly",
  "animation": "greeting",
  "lookAt": { "x": 0, "y": 0, "z": 1 }
}
```

**アクション:**
- `update`: 複数のプロパティを更新
- `setExpression`: 表情を設定
- `playAnimation`: アニメーションを再生
- `setLookAt`: 視線方向を設定
- `reset`: デフォルト状態にリセット

**利用可能な表情:**
- `neutral`: 通常
- `happy`: 喜び
- `sad`: 悲しみ
- `angry`: 怒り
- `surprised`: 驚き
- `thinking`: 考え中
- `friendly`: 親しみやすい
- `explaining`: 説明中

**利用可能なアニメーション:**
- `idle`: アイドル
- `greeting`: 挨拶
- `talking`: 話し中
- `listening`: 聞いている
- `thinking`: 考えている
- `pointing`: 指差し
- `bowing`: お辞儀
- `waving`: 手を振る

#### レスポンス
```json
{
  "success": true,
  "characterState": {
    "expression": "friendly",
    "animation": "greeting",
    "lookAt": { "x": 0, "y": 0, "z": 1 }
  }
}
```

## ❓ Q&A API

### POST /api/qa

RAG（検索拡張生成）による質問応答

#### リクエスト
```json
{
  "action": "ask",
  "question": "エンジニアカフェの利用料金は？",
  "language": "ja",
  "sessionId": "セッションID"
}
```

#### レスポンス
```json
{
  "success": true,
  "answer": "エンジニアカフェは基本的に無料でご利用いただけます。",
  "sources": [
    {
      "title": "料金について",
      "content": "...",
      "relevance": 0.95
    }
  ],
  "suggestedQuestions": [
    "会員登録は必要ですか？",
    "営業時間を教えてください"
  ]
}
```

## 🔗 外部連携API

### POST /api/external

外部システムとの統合

#### リクエスト
```json
{
  "action": "sendToReception",
  "visitorInfo": {
    "name": "山田太郎",
    "purpose": "workshop",
    "language": "ja"
  }
}
```

**アクション:**
- `sendToReception`: 受付に情報送信
- `getReceptionStatus`: 受付状況取得
- `websocket`: WebSocketイベント送信

## 🏞️ 背景API

### GET /api/backgrounds

アプリケーションで利用可能な背景画像を取得します。

#### リクエスト

パラメータは不要です。

#### レスポンス

**成功 (200):**
```json
{
  "images": [
    "IMG_5573.JPG",
    "placeholder.svg"
  ],
  "total": 2
}
```

**注記:**
- `/public/backgrounds` ディレクトリ内のすべての画像ファイルを返します
- サポート形式: `.jpg`, `.jpeg`, `.png`, `.webp`, `.svg`
- 隠しファイル（`.`で始まる）とREADMEファイルは除外されます
- ディレクトリが存在しない場合は自動的に作成されます
```

## 🚨 エラー処理

### エラーレスポンス形式
```json
{
  "error": "エラーメッセージ",
  "details": "詳細なエラー情報",
  "code": "ERROR_CODE",
  "timestamp": "2025-05-30T12:00:00Z"
}
```

### 一般的なエラーコード
- `INVALID_REQUEST`: 無効なリクエストパラメータ
- `SESSION_NOT_FOUND`: セッションIDが見つからないか期限切れ
- `AUDIO_PROCESSING_ERROR`: 音声処理エラー
- `AI_GENERATION_ERROR`: AI応答生成エラー
- `CHARACTER_LOAD_ERROR`: キャラクターモデル読み込みエラー
- `SLIDE_NOT_FOUND`: スライドファイルが見つからない
- `EXTERNAL_API_ERROR`: 外部API接続エラー
- `RATE_LIMIT_EXCEEDED`: リクエスト数制限超過

### HTTPステータスコード
- `200 OK`: リクエスト成功
- `400 Bad Request`: 無効なパラメータ
- `401 Unauthorized`: 認証が必要
- `404 Not Found`: リソースが見つからない
- `429 Too Many Requests`: レート制限超過
- `500 Internal Server Error`: サーバーエラー

## 🔒 レート制限

APIの悪用を防ぐためのレート制限：

### 制限値
- 音声API: 10リクエスト/10秒/セッション
- スライドAPI: 30リクエスト/分
- キャラクターAPI: 60リクエスト/分
- Q&A API: 20リクエスト/分
- 外部API: 10リクエスト/分

### レート制限ヘッダー
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1717066860
```

## 💻 コード例

### JavaScript/TypeScript

```typescript
// セッション開始と音声処理
async function startVoiceConversation() {
  // セッション開始
  const sessionRes = await fetch('/api/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'start_session',
      language: 'ja'
    })
  });
  
  const { sessionId } = await sessionRes.json();
  
  // 音声入力処理
  const audioData = await recordAudio(); // 音声録音関数
  const audioBase64 = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(audioData))));
  
  const voiceRes = await fetch('/api/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'process_voice',
      audioData: audioBase64,
      sessionId
    })
  });
  
  const result = await voiceRes.json();
  console.log('文字起こし:', result.transcript);
  console.log('応答:', result.response);
  
  // 音声応答を再生
  const audio = new Audio(`data:audio/mp3;base64,${result.audioResponse}`);
  await audio.play();
}
```

### Python

```python
import requests
import base64

# セッション開始
session_res = requests.post('http://localhost:3000/api/voice', json={
    'action': 'start_session',
    'language': 'ja'
})
session_id = session_res.json()['sessionId']

# 音声処理
with open('audio.webm', 'rb') as f:
    audio_data = base64.b64encode(f.read()).decode('utf-8')

voice_res = requests.post('http://localhost:3000/api/voice', json={
    'action': 'process_voice',
    'audioData': audio_data,
    'sessionId': session_id
})

result = voice_res.json()
print(f"文字起こし: {result['transcript']}")
print(f"応答: {result['response']}")
```

### cURL

```bash
# セッション開始
curl -X POST http://localhost:3000/api/voice \
  -H "Content-Type: application/json" \
  -d '{"action": "start_session", "language": "ja"}'

# ステータス確認
curl http://localhost:3000/api/voice?action=status

# サポート言語取得
curl http://localhost:3000/api/voice?action=supported_languages
```

## 📚 ベストプラクティス

1. **セッション管理**: 音声処理の前に必ずセッションを開始
2. **エラーハンドリング**: 一時的な障害に対するリトライロジックの実装
3. **音声形式**: 最高の圧縮と品質のためWebM Opusを使用
4. **言語検出**: 可能な限りシステムに言語を自動検出させる
5. **キャラクター更新**: API呼び出しを減らすためバッチ更新を行う
6. **キャッシング**: 可能な限りスライドコンテンツとキャラクター状態をキャッシュ

## 📋 更新履歴

### v2.0.0 (2025-05-30)
- Service Account認証のサポート
- Next.js互換性のための簡略化された音声サービス
- Supabaseメモリアダプタ統合
- マルチターン会話のサポート
- セッション管理の改善
- 感情検出機能の追加

### v2.1.0 (2025-06-30)
- SimplifiedMemorySystemによる3分間TTLメモリ
- クロス言語検索対応のマルチ言語RAG
- Web Audio APIによるモバイル音声互換性
- インテリジェントキャッシング付きリップシンク最適化
- 本番環境監視ダッシュボード
- 知識更新用自動CRONジョブ
- 管理者向け知識管理インターフェース
- メモリを意識した会話処理

### v1.2.0 (2024-01-30)
- 背景制御API追加

### v1.1.0 (2024-01-25)
- セキュリティ強化、XSS保護

### v1.0.0 (2024-01-20)
- 初期APIリリース

---

## 🔍 知識ベース検索API

### POST /api/knowledge/search

マルチ言語対応のRAG（検索拡張生成）ベースの知識ベース検索。

#### リクエスト

```json
{
  "query": "エンジニアカフェの利用時間は？",
  "language": "ja",
  "limit": 5,
  "similarityThreshold": 0.7
}
```

#### レスポンス

```json
{
  "success": true,
  "results": [
    {
      "content": "エンジニアカフェの営業時間は9:00-22:00です",
      "similarity": 0.85,
      "metadata": {
        "source": "facility-info",
        "category": "基本情報",
        "subcategory": "営業時間",
        "language": "ja",
        "importance": "high"
      }
    }
  ],
  "total": 1,
  "embeddingModel": "text-embedding-004",
  "searchLanguage": "ja"
}
```

**機能:**
- クロス言語検索: 英語の質問で日本語コンテンツを検索可能
- Google text-embedding-004使用（768次元、1536次元にパディング）
- OpenAI text-embedding-3-smallへのフォールバック
- クロス言語結果の自動重複除去

## 📊 監視API

### GET /api/monitoring/dashboard

システム監視ダッシュボード用データの取得。

#### レスポンス

```json
{
  "success": true,
  "metrics": {
    "ragSearchMetrics": {
      "totalSearches": 1250,
      "avgLatency": 580,
      "successRate": 0.95
    },
    "cacheMetrics": {
      "hitRate": 0.82,
      "totalHits": 1025
    },
    "externalApiMetrics": {
      "connpass": {
        "totalCalls": 48,
        "avgLatency": 1200
      }
    },
    "systemHealth": {
      "status": "healthy",
      "uptime": 99.95
    }
  }
}
```

## 🤖 管理API

### GET /admin/knowledge

Webベースの知識ベース管理インターフェース。

### POST /api/admin/knowledge/import

重複検出付きバッチインポート。

## 🔄 CRON API

### POST /api/cron/update-knowledge-base

外部ソースからの自動知識ベース同期。

**ヘッダー:**
```http
Authorization: Bearer your-cron-secret
```

**機能:**
- 本番環境では6時間ごとに実行
- Connpass、Googleカレンダー、Webサイトから同期
- 期限切れイベントの自動クリーンアップ
- マルチ言語コンテンツ生成

### POST /api/cron/update-slides

スライドコンテンツの自動更新。

## 🏥 ヘルスチェックAPI

### GET /api/health/knowledge

知識ベースの健全性ステータス。

#### レスポンス

```json
{
  "success": true,
  "health": {
    "totalEntries": 84,
    "languages": {
      "ja": 42,
      "en": 42
    },
    "lastUpdate": "2025-06-30T12:00:00Z",
    "embeddingModel": "text-embedding-004",
    "status": "healthy"
  }
}
```

詳細については[メインドキュメント](./README.md)を参照するか、開発チームにお問い合わせください。

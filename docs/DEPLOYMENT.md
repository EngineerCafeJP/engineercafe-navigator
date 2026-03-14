# デプロイメントガイド

> 注意: この文書には Vercel 前提の記述が残っている可能性があります。現行の deploy 判断は `docs/STATUS.md` と `docs/DEVELOPER-GUIDE.md` を優先してください。

> Engineer Cafe Navigator 本番環境デプロイ手順書

## 📖 概要

このドキュメントは Engineer Cafe Navigator を本番環境にデプロイするための詳細な手順とベストプラクティスをまとめています。

## 🏗️ インフラストラクチャ構成

### 推奨構成

```mermaid
graph TB
    subgraph "CDN/Edge"
        CF[Cloudflare/Vercel Edge]
    end
    
    subgraph "Frontend"
        V[Vercel]
        N[Next.js 15]
    end
    
    subgraph "Backend Services"
        G[Google Cloud]
        S[Supabase]
    end
    
    subgraph "Monitoring"
        M[Monitoring Services]
        L[Logging]
    end
    
    CF --> V
    V --> N
    N --> G
    N --> S
    V --> M
    V --> L
```

### サービス詳細

| サービス | 用途 | 推奨プロバイダー | 料金目安 |
|----------|------|------------------|----------|
| **ホスティング** | Next.js アプリケーション | Vercel Pro | $20/月 |
| **データベース** | PostgreSQL + pgvector | Supabase Pro | $25/月 |
| **音声API** | 音声認識・合成 | Google Cloud | 従量課金 |
| **AI API** | Gemini 2.5 Flash | Google AI | 従量課金 |
| **CDN** | 静的アセット配信 | Vercel/Cloudflare | 含む |
| **監視** | エラー追跡・監視 | Vercel Analytics | 含む |

## 🚀 デプロイ手順

### 1. 事前準備

#### 必要なアカウント・API キー

```bash
# 1. Vercelアカウント作成
https://vercel.com/signup

# 2. Supabaseプロジェクト作成
https://supabase.com/dashboard

# 3. Google Cloud プロジェクト作成
https://console.cloud.google.com

# 4. Google AI API キー取得
https://makersuite.google.com/app/apikey
```

#### ローカル環境での最終確認

```bash
# 依存関係インストール
pnpm install

# 型チェック
pnpm run type-check

# リントチェック
pnpm run lint

# テスト実行
pnpm run test

# 本番ビルド確認
pnpm run build
pnpm run start
```

### 2. Supabase データベース設定

#### プロジェクト作成

```bash
# Supabase CLI インストール
npm install -g supabase

# ログイン
supabase login

# プロジェクト初期化
supabase init
```

#### データベース設定

```sql
-- pgvector拡張の有効化
CREATE EXTENSION IF NOT EXISTS vector;

-- セッション管理テーブル
CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  data JSONB NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- インデックス作成
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);

-- 期限切れセッション自動削除
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
  DELETE FROM sessions WHERE expires_at < now();
END;
$$ LANGUAGE plpgsql;

-- 定期実行設定（1時間毎）
SELECT cron.schedule('cleanup-sessions', '0 * * * *', 'SELECT cleanup_expired_sessions();');
```

#### セキュリティ設定

```sql
-- RLS (Row Level Security) 有効化
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- セッション所有者のみアクセス可能
CREATE POLICY "Users can only access their own sessions" ON sessions
  FOR ALL USING (auth.uid()::text = id::text);
```

### 3. Google Cloud 設定

#### API有効化

```bash
# Google Cloud CLI インストール
curl https://sdk.cloud.google.com | bash

# ログイン
gcloud auth login

# プロジェクト設定
gcloud config set project YOUR_PROJECT_ID

# 必要なAPI有効化
gcloud services enable speech.googleapis.com
gcloud services enable texttospeech.googleapis.com
gcloud services enable translate.googleapis.com
```

#### サービスアカウント作成

```bash
# サービスアカウント作成
gcloud iam service-accounts create engineer-cafe-navigator \
  --display-name="Engineer Cafe Navigator"

# 権限付与
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:engineer-cafe-navigator@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/speech.client"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:engineer-cafe-navigator@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/texttospeech.client"

# キーファイル作成
gcloud iam service-accounts keys create config/service-account-key.json \
  --iam-account=engineer-cafe-navigator@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 4. Vercel デプロイ

#### プロジェクト設定

```bash
# Vercel CLI インストール
npm install -g vercel

# ログイン
vercel login

# プロジェクト初期化
vercel

# 設定確認
vercel inspect
```

#### 環境変数設定

```bash
# Vercelプロジェクトで設定
vercel env add GOOGLE_GENERATIVE_AI_API_KEY
vercel env add GOOGLE_CLOUD_PROJECT_ID
vercel env add OPENAI_API_KEY
vercel env add POSTGRES_URL
vercel env add NEXTAUTH_SECRET
vercel env add NEXTAUTH_URL

# または、Vercelダッシュボードで設定
# https://vercel.com/dashboard -> Project -> Settings -> Environment Variables
```

#### 本番デプロイ

```bash
# 本番環境にデプロイ
vercel --prod

# デプロイ状況確認
vercel ls
```

### 5. カスタムドメイン設定

#### DNS設定

```bash
# Vercelでドメイン追加
vercel domains add engineer-cafe-navigator.com

# DNS設定確認
dig engineer-cafe-navigator.com
```

#### SSL/TLS設定

```bash
# SSL証明書は自動で設定されます
# 設定確認
curl -I https://engineer-cafe-navigator.com
```

### 6. RAG システム設定

#### データベースマイグレーション

```bash
# Production環境でRAG関連テーブルとインデックスを作成
supabase db push

# pgvector拡張の確認
psql $POSTGRES_URL -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# RAG検索関数の作成
psql $POSTGRES_URL -f supabase/migrations/20250601000000_add_knowledge_base_search.sql
```

#### 初期知識ベースのシード

```bash
# 本番環境変数を設定
export NODE_ENV=production

# 知識ベースの初期データを投入
pnpm seed:knowledge

# 投入データの確認
pnpm test:rag
```

#### 外部API設定

```env
# Connpass API (レート制限: 10回/分)
CONNPASS_API_ENABLED=true

# Google Calendar API
GOOGLE_CALENDAR_CLIENT_ID=your-client-id
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_REDIRECT_URI=https://engineer-cafe-navigator.com/api/auth/google/callback
ENGINEER_CAFE_CALENDAR_ID=your-calendar-id@group.calendar.google.com

# Web Scraping
ENGINEER_CAFE_WEBSITE_URL=https://engineer-cafe.jp
SCRAPING_USER_AGENT=EngineerCafeNavigator/1.0

# Cache設定 (Upstash Redis)
UPSTASH_REDIS_URL=your-redis-url
UPSTASH_REDIS_TOKEN=your-redis-token
```

#### CRON ジョブ設定

```typescript
// vercel.json に追加
{
  "crons": [
    {
      "path": "/api/cron/update-knowledge-base",
      "schedule": "0 */6 * * *"  // 6時間ごと
    },
    {
      "path": "/api/cron/update-slides",
      "schedule": "0 0 * * *"  // 毎日午前0時
    }
  ]
}
```

#### CRON ジョブセキュリティ

```typescript
// api/cron/update-knowledge-base/route.ts
export async function POST(request: NextRequest) {
  // CRONシークレット検証
  const authHeader = request.headers.get('authorization');
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  
  // 知識ベース更新処理
  // ...
}
```

#### RAG パフォーマンス最適化

```sql
-- IVFFlat インデックスの作成（本番環境）
CREATE INDEX idx_knowledge_base_embedding_ivfflat 
ON knowledge_base USING ivfflat (content_embedding vector_cosine_ops)
WITH (lists = 100);

-- 検索パフォーマンスの確認
EXPLAIN ANALYZE
SELECT * FROM search_knowledge_base(
  '[0.1, 0.2, ...]'::vector(1536),
  0.7,
  5
);
```

## ⚙️ 本番環境設定

### 1. 環境変数

#### 必須環境変数

```env
# Google AI
GOOGLE_GENERATIVE_AI_API_KEY=your-gemini-api-key

# Google Cloud
GOOGLE_CLOUD_PROJECT_ID=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# OpenAI (Embeddings - 1536 dimensions)
OPENAI_API_KEY=your-openai-api-key

# Database
POSTGRES_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
SUPABASE_URL=https://[project-ref].supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Authentication
NEXTAUTH_SECRET=your-32-character-secret-key
NEXTAUTH_URL=https://engineer-cafe-navigator.com

# CRON Jobs
CRON_SECRET=your-cron-secret

# Optional: External Services
WEBSOCKET_URL=wss://your-websocket-server.com
RECEPTION_API_URL=https://your-reception-api.com
GOOGLE_CALENDAR_CLIENT_ID=your-client-id
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
```

#### セキュリティ設定

```env
# セキュリティヘッダー
SECURITY_HEADERS=true
CSP_POLICY="default-src 'self'; script-src 'self' 'unsafe-inline'"

# レート制限
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX=10
RATE_LIMIT_WINDOW=10000

# ログレベル
LOG_LEVEL=info
ERROR_REPORTING=true
```

### 2. Next.js 本番設定

#### next.config.js

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  // パフォーマンス最適化
  experimental: {
    optimizeCss: true,
    optimizeServerReact: true,
  },
  
  // 静的アセット最適化
  images: {
    domains: ['your-domain.com'],
    formats: ['image/webp', 'image/avif'],
  },
  
  // セキュリティヘッダー
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin'
          },
          {
            key: 'Permissions-Policy',
            value: 'microphone=(self), camera=(), geolocation=()'
          },
          {
            key: 'Content-Security-Policy',
            value: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.googleapis.com https://*.supabase.co;"
          }
        ]
      }
    ];
  },
  
  // リダイレクト設定
  async redirects() {
    return [
      {
        source: '/admin',
        destination: '/dashboard',
        permanent: true,
      },
    ];
  },
};

module.exports = nextConfig;
```

### 3. パフォーマンス最適化

#### バンドル最適化

```javascript
// webpack設定（next.config.js内）
const config = {
  webpack: (config, { buildId, dev, isServer, defaultLoaders, webpack }) => {
    // 本番環境でのバンドル最適化
    if (!dev) {
      config.optimization.splitChunks = {
        chunks: 'all',
        cacheGroups: {
          vendor: {
            test: /[\\/]node_modules[\\/]/,
            name: 'vendors',
            priority: 10,
            enforce: true,
          },
        },
      };
    }
    
    return config;
  },
};
```

#### 画像最適化

```typescript
// VRMモデルの最適化
const optimizeVRMModel = async (modelPath: string) => {
  // モデルファイルサイズ確認
  const stats = await fs.stat(modelPath);
  if (stats.size > 10 * 1024 * 1024) { // 10MB
    console.warn('VRMモデルが大きすぎます:', stats.size);
  }
  
  // 圧縮版の使用
  const compressedPath = modelPath.replace('.vrm', '.compressed.vrm');
  if (await fs.access(compressedPath).then(() => true).catch(() => false)) {
    return compressedPath;
  }
  
  return modelPath;
};
```

## 📊 監視・ログ設定

### 1. Vercel Analytics

```typescript
// app/layout.tsx
import { Analytics } from '@vercel/analytics/react';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
```

### 2. エラー監視

```typescript
// lib/monitoring.ts
const logError = (error: Error, context?: Record<string, any>) => {
  // 本番環境での包括的エラーログ
  const errorInfo = {
    message: error.message,
    stack: error.stack,
    timestamp: new Date().toISOString(),
    url: typeof window !== 'undefined' ? window.location.href : 'server',
    userAgent: typeof window !== 'undefined' ? window.navigator.userAgent : 'server',
    context,
  };
  
  console.error('Application Error:', errorInfo);
  
  // 外部監視サービスへの送信（Sentry、DataDog等）
  if (process.env.NODE_ENV === 'production') {
    // sendToMonitoringService(errorInfo);
  }
};

// APIエラーログ
export const logApiError = (
  endpoint: string,
  method: string,
  error: Error,
  requestData?: any
) => {
  logError(error, {
    type: 'api_error',
    endpoint,
    method,
    requestData: requestData ? JSON.stringify(requestData) : undefined,
  });
};

// クライアントエラーログ
export const logClientError = (error: Error, componentName?: string) => {
  logError(error, {
    type: 'client_error',
    component: componentName,
  });
};
```

### 3. パフォーマンス監視

```typescript
// lib/performance.ts
export const measureApiPerformance = async <T>(
  endpoint: string,
  operation: () => Promise<T>
): Promise<T> => {
  const start = performance.now();
  
  try {
    const result = await operation();
    const duration = performance.now() - start;
    
    // パフォーマンスメトリクス記録
    if (typeof window !== 'undefined') {
      window.gtag?.('event', 'api_performance', {
        endpoint,
        duration: Math.round(duration),
        status: 'success',
      });
    }
    
    console.log(`API Performance [${endpoint}]: ${duration.toFixed(2)}ms`);
    return result;
    
  } catch (error) {
    const duration = performance.now() - start;
    
    if (typeof window !== 'undefined') {
      window.gtag?.('event', 'api_performance', {
        endpoint,
        duration: Math.round(duration),
        status: 'error',
      });
    }
    
    throw error;
  }
};
```

## 🔄 CI/CD パイプライン

### 1. GitHub Actions設定

```yaml
# .github/workflows/production.yml
name: Production Deployment

on:
  push:
    branches: [main]
  
env:
  VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
  VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

jobs:
  quality-check:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'pnpm'
      
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
      
      - name: Type checking
        run: pnpm run type-check
      
      - name: Linting
        run: pnpm run lint
      
      - name: Testing
        run: pnpm run test
      
      - name: Security audit
        run: pnpm audit --audit-level moderate
      
      - name: Build test
        run: pnpm run build

  deploy:
    needs: quality-check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3
      
      - name: Install Vercel CLI
        run: npm install --global vercel@latest
      
      - name: Pull Vercel Environment Information
        run: vercel pull --yes --environment=production --token=${{ secrets.VERCEL_TOKEN }}
      
      - name: Build Project Artifacts
        run: vercel build --prod --token=${{ secrets.VERCEL_TOKEN }}
      
      - name: Deploy Project Artifacts to Vercel
        run: vercel deploy --prebuilt --prod --token=${{ secrets.VERCEL_TOKEN }}

  health-check:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - name: Health Check
        run: |
          curl -f https://engineer-cafe-navigator.com/api/voice?action=status || exit 1
          curl -f https://engineer-cafe-navigator.com/api/character?action=health || exit 1
```

### 2. デプロイ後検証

```bash
#!/bin/bash
# scripts/post-deploy-check.sh

echo "🚀 デプロイ後検証開始..."

# ヘルスチェック
echo "📡 APIヘルスチェック..."
curl -f "$VERCEL_URL/api/voice?action=status" || { echo "❌ Voice API失敗"; exit 1; }
curl -f "$VERCEL_URL/api/character?action=health" || { echo "❌ Character API失敗"; exit 1; }
curl -f "$VERCEL_URL/api/marp?action=health" || { echo "❌ Marp API失敗"; exit 1; }

# パフォーマンステスト
echo "⚡ パフォーマンステスト..."
RESPONSE_TIME=$(curl -w "%{time_total}" -s -o /dev/null "$VERCEL_URL")
if (( $(echo "$RESPONSE_TIME > 2.0" | bc -l) )); then
  echo "⚠️  警告: レスポンス時間が遅い ($RESPONSE_TIME秒)"
fi

# セキュリティヘッダー確認
echo "🔒 セキュリティヘッダー確認..."
HEADERS=$(curl -I -s "$VERCEL_URL")
echo "$HEADERS" | grep -q "X-Frame-Options" || { echo "❌ X-Frame-Options未設定"; exit 1; }
echo "$HEADERS" | grep -q "X-Content-Type-Options" || { echo "❌ X-Content-Type-Options未設定"; exit 1; }

echo "✅ デプロイ後検証完了!"
```

## 📦 本番環境固有の設定

### 監視ダッシュボード

```typescript
// /api/monitoring/dashboardのレスポンス
{
  "ragSearchMetrics": {
    "totalSearches": 1250,
    "avgLatency": 580,
    "successRate": 0.95
  },
  "cacheMetrics": {
    "hitRate": 0.82,
    "totalHits": 1025,
    "totalMisses": 225
  },
  "externalApiMetrics": {
    "connpass": {
      "totalCalls": 48,
      "avgLatency": 1200,
      "errorRate": 0.02
    },
    "googleCalendar": {
      "totalCalls": 96,
      "avgLatency": 800,
      "errorRate": 0.01
    }
  },
  "systemHealth": {
    "status": "healthy",
    "uptime": 99.95,
    "lastError": null
  }
}
```

### アラート設定

```bash
# Webhook URLの設定
vercel env add ALERT_WEBHOOK_URL production
vercel env add ALERT_WEBHOOK_SECRET production

# アラート条件
- RAG検索レイテンシ > 2秒
- キャッシュヒット率 < 60%
- エラー率 > 5%
- システムステータス != healthy
```

## 🔧 トラブルシューティング

### 1. よくある問題と解決方法

#### ビルドエラー

```bash
# 型エラー
Error: Type 'undefined' is not assignable to type 'string'

# 解決方法
# 1. 型定義の確認
pnpm run type-check

# 2. 依存関係の再インストール
rm -rf node_modules pnpm-lock.yaml
pnpm install

# 3. Next.js キャッシュクリア
pnpm run dev:clean
```

#### 環境変数エラー

```bash
# エラー例
Error: Missing required environment variable: GOOGLE_GENERATIVE_AI_API_KEY

# 確認方法
vercel env ls

# 設定方法
vercel env add GOOGLE_GENERATIVE_AI_API_KEY production
```

#### データベース接続エラー

```bash
# エラー例
Error: database "postgres" does not exist

# 確認手順
1. Supabaseプロジェクト状態確認
2. 接続文字列の確認
3. pgvector拡張の確認

# 解決方法
psql $POSTGRES_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. パフォーマンス問題

#### iPad/iOSの音声問題

```typescript
// 問題
AudioContextがSafariでブロックされる

// 解決策
1. MobileAudioServiceが自動的にフォールバック
2. ユーザーにタップを促すUI表示
3. AudioInteractionManagerがイベントをキャッチ
```

#### 遅いAPIレスポンス

```typescript
// 原因調査
const debugApiPerformance = async () => {
  console.time('API Call');
  
  try {
    const response = await fetch('/api/voice', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    
    console.timeEnd('API Call');
    
    if (!response.ok) {
      console.error('API Error:', response.status, response.statusText);
    }
    
  } catch (error) {
    console.timeEnd('API Call');
    console.error('Network Error:', error);
  }
};

// 解決策
1. レスポンスサイズの最適化
2. キャッシュの活用
3. 並列処理の実装
4. タイムアウト設定の調整
```

#### メモリリーク

```typescript
// 原因調査
const memoryUsage = () => {
  if (typeof window !== 'undefined' && 'memory' in performance) {
    const memory = (performance as any).memory;
    console.log('Memory Usage:', {
      used: Math.round(memory.usedJSHeapSize / 1024 / 1024) + ' MB',
      total: Math.round(memory.totalJSHeapSize / 1024 / 1024) + ' MB',
      limit: Math.round(memory.jsHeapSizeLimit / 1024 / 1024) + ' MB',
    });
  }
};

// 解決策
1. useEffectのクリーンアップ関数実装
2. イベントリスナーの適切な削除
3. タイマーのクリア
4. 大きなオブジェクトの明示的な削除
```

## 📋 デプロイチェックリスト

### デプロイ前

- [ ] コードレビュー完了
- [ ] 全テスト通過
- [ ] セキュリティ監査実施
- [ ] パフォーマンステスト実施
- [ ] 環境変数設定確認
- [ ] データベースマイグレーション実行
- [ ] バックアップ作成

### デプロイ後

- [ ] ヘルスチェック実行
- [ ] 全機能動作確認
- [ ] パフォーマンス監視
- [ ] エラーログ監視
- [ ] セキュリティヘッダー確認
- [ ] SSL/TLS証明書確認
- [ ] DNS設定確認
- [ ] RAG検索機能の動作確認
- [ ] 外部API接続確認（Connpass、Google Calendar）
- [ ] 知識ベース更新ジョブの稼働確認
- [ ] スライド更新ジョブの稼働確認
- [ ] 監視ダッシュボードの動作確認
- [ ] アラートWebhookの設定確認

### 緊急時対応

- [ ] ロールバック手順確認
- [ ] 緊急連絡先リスト更新
- [ ] インシデント対応手順書確認
- [ ] バックアップからの復旧手順確認

## 📞 サポート・連絡先

### デプロイサポート

- **技術サポート**: tech-support@engineer-cafe.jp
- **緊急連絡**: +81-XXX-XXXX-XXXX
- **ドキュメント**: [内部Wiki](https://wiki.engineer-cafe.jp)

### 外部サービスサポート

- **Vercel**: https://vercel.com/help
- **Supabase**: https://supabase.com/docs
- **Google Cloud**: https://cloud.google.com/support

---

<div align="center">

**🚀 Successful Deployment - Engineer Cafe Navigator**

[🏠 ホーム](../README.md) • [📖 開発ガイド](DEVELOPMENT.md) • [🔒 セキュリティ](SECURITY.md)

</div>

# Engineer Cafe Navigator - Development Workflow

## Development Environment Setup

### Prerequisites
- Node.js >= 18.0.0
- pnpm >= 8.0.0
- Python >= 3.11.0 (for backend)

### Initial Setup
```bash
# Clone and install
git clone <repository>
cd engineer-cafe-navigator2025
pnpm install

# Frontend dependencies
cd frontend && pnpm install

# Backend dependencies (optional)
cd ../backend && pip install -r requirements.txt
```

### Environment Configuration

**Frontend (frontend/.env.local)**
```env
# Required
GOOGLE_CLOUD_PROJECT_ID=your_project_id
GOOGLE_GENERATIVE_AI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key

# Google Cloud Service Account
# Place service-account-key.json in frontend/config/

# Optional
CRON_SECRET=your_cron_secret
ALERT_WEBHOOK_SECRET=your_alert_secret
```

**Backend (backend/.env)**
```env
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
ENVIRONMENT=development
```

## Running the Application

### Development Mode
```bash
# From root - starts both frontend and backend
pnpm dev

# Frontend only (localhost:3000)
pnpm dev:frontend

# Backend only (localhost:8000)
pnpm dev:backend
```

### Production Build
```bash
cd frontend
pnpm build
pnpm start
```

## Common Development Tasks

### Adding a New Agent

1. Create agent file in `/frontend/src/mastra/agents/`
2. Import in `/frontend/src/mastra/index.ts`
3. Register in `EngineerCafeNavigator.initializeAgents()`
4. Update `MainQAWorkflow` routing logic

### Adding Knowledge Base Entries

```bash
# Via Admin UI
http://localhost:3000/admin/knowledge

# Via Script
cd frontend
pnpm seed:knowledge
pnpm import:knowledge
```

### Adding STT Corrections

Edit `/frontend/src/lib/stt-correction.ts`:
```typescript
corrections.push({
  pattern: /incorrect_pattern/gi,
  replacement: 'correct_term',
  contextRegex: /optional_context/gi  // Optional
});
```

### Adding New API Endpoint

Create route file in `/frontend/src/app/api/{endpoint}/route.ts`:
```typescript
export async function POST(request: NextRequest) {
  // Implementation
}

export async function GET(request: NextRequest) {
  // Implementation
}
```

## Code Quality

### Linting & Type Checking
```bash
cd frontend
pnpm lint          # ESLint
pnpm typecheck     # TypeScript
```

### Pre-commit Checklist
1. Run `pnpm lint` - fix any errors
2. Run `pnpm typecheck` - fix type errors
3. Test voice interactions manually
4. Verify RAG search results

## Testing

### Manual Testing Endpoints
- Voice API: `POST /api/voice` with `action: 'process_voice'`
- Q&A API: `POST /api/qa` with `action: 'ask_question'`
- RAG Search: `POST /api/knowledge/search`

### Test Knowledge Base
```bash
cd frontend
pnpm test:rag      # Test RAG functionality
pnpm test:api      # Test API endpoints
```

### Monitoring Dashboard
Access: `http://localhost:3000/api/monitoring/dashboard`

## Deployment

### Vercel (Frontend)
- Configure environment variables in Vercel dashboard
- Deploy from main branch

### CRON Jobs
- Automatic knowledge base updates every 6 hours
- Requires `CRON_SECRET` configuration

## Critical Warnings

### ⚠️ Tailwind CSS Version
**MUST use v3.4.17** - v4 has breaking changes
```bash
# If dependencies are wrong, run:
cd frontend && pnpm install:css
```

### ⚠️ Embedding Dimensions
- Always use 1536 dimensions (OpenAI text-embedding-3-small)
- Do NOT use 768 dimensions (deprecated)

### ⚠️ Mobile Audio
- iOS requires user interaction for AudioContext
- Test on real devices, not simulators

### ⚠️ Memory TTL
- 3-minute TTL for conversation context
- Longer conversations may lose early context

## Debugging Tips

### Voice Processing Issues
1. Check Google Cloud credentials
2. Verify service account permissions
3. Check STT correction logs

### RAG Search Issues
1. Verify embeddings are 1536D
2. Check similarity threshold (default 0.5)
3. Test with `/api/knowledge/search` directly

### Memory System Issues
1. Check `agent_memory` table in Supabase
2. Verify TTL expiration is working
3. Check agent namespace isolation

### Character/Lip-sync Issues
1. Clear lip-sync cache in settings panel
2. Check AudioContext state
3. Test on desktop first before mobile

---

## Supabase ローカル環境

### セットアップ

```bash
cd frontend

# Supabase CLI インストール (未インストールの場合)
brew install supabase/tap/supabase

# ローカル環境起動 (Docker必須)
supabase start
```

### 接続情報

| サービス | URL |
|---------|-----|
| API | http://127.0.0.1:54321 |
| Studio | http://127.0.0.1:54323 |
| Database | postgresql://postgres:postgres@127.0.0.1:54322/postgres |

### ローカル用 .env.local 設定

```env
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase start で表示される anon key>
SUPABASE_SERVICE_ROLE_KEY=<supabase start で表示される service_role key>
```

### マイグレーションファイル

```
frontend/supabase/migrations/
├── 20250529005253_init_engineer_cafe_navigator.sql  # 初期スキーマ
├── 20250601000000_add_knowledge_base_search.sql     # ベクトル検索RPC
├── 20250601010000_add_analytics_tables.sql          # 分析
├── 20250607000000_add_metrics_tables.sql            # メトリクス
└── 20250607010000_add_production_monitoring.sql     # 監視
```

### 便利なコマンド

```bash
supabase stop              # 停止
supabase stop --backup     # データ保持して停止
supabase db reset          # マイグレーションリセット
supabase migration list    # マイグレーション状態確認
```

---

## LangGraph 開発

### バックエンド構成

```
backend/
├── src/
│   ├── main.py           # FastAPI エントリーポイント
│   ├── agents/           # LangGraphエージェント
│   └── models/           # Pydantic モデル
├── requirements.txt
└── .env.example
```

### セットアップ

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload --port 8000
```

### 主要依存関係

- langgraph>=0.2.0
- langchain>=0.3.0
- langchain-openai>=0.2.0
- langchain-google-genai>=2.0.0
- fastapi>=0.115.0
- supabase>=2.0.0

### 参考実装

`langgraph-reference/coworking-space-system/` に完全な動作サンプルあり。

---

## 開発ドキュメント

| ドキュメント | 内容 |
|------------|------|
| `/docs/LOCAL-DEVELOPMENT-SETUP.md` | 総合セットアップガイド |
| `/docs/LANGGRAPH-DEVELOPMENT-GUIDE.md` | LangGraph開発詳細 |
| `/docs/migration/agents/` | エージェント移行仕様 |

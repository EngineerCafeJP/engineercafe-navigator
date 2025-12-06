# Engineer Cafe Navigator - Project Onboarding

## Project Overview

Engineer Cafe Navigator is a multilingual voice AI navigation system for the Engineer Cafe facility in Fukuoka's Aka-Renga Cultural Center. The system enables natural language interactions through a 3D VRM character avatar.

**Last Updated:** 2025-12-06

## Repository Structure (Monorepo)

```
engineer-cafe-navigator2025/
├── frontend/              # NextJS 15.3.2 + Mastra 0.10.5 (PRODUCTION)
│   ├── src/
│   │   ├── app/          # Next.js App Router pages and API routes
│   │   ├── mastra/       # AI agent system (8 specialized agents)
│   │   ├── lib/          # Core libraries (memory, audio, RAG)
│   │   └── components/   # React UI components
│   └── public/           # Static assets (VRM models, backgrounds)
├── backend/              # Python FastAPI + LangGraph (IN DEVELOPMENT)
│   ├── main.py           # FastAPI application
│   ├── workflows/        # LangGraph workflow definitions
│   └── agents/           # Agent implementations (TODO)
├── docs/                 # Documentation
└── package.json          # Root workspace configuration
```

## Technology Stack

### Frontend (Production)
- **Framework**: Next.js 15.3.2 (App Router) + React 19.1.0 + TypeScript 5.8.3
- **AI Framework**: Mastra 0.10.5 for agent orchestration
- **AI Models**: 
  - Google Gemini 2.5 Flash Preview (response generation)
  - OpenAI text-embedding-3-small (1536D for RAG embeddings)
- **Voice**: Google Cloud Speech-to-Text/Text-to-Speech
- **3D Graphics**: Three.js 0.176.0 + @pixiv/three-vrm 3.4.1
- **Database**: Supabase (PostgreSQL with pgvector)
- **CSS**: Tailwind CSS v3.4.17 (DO NOT upgrade to v4!)

### Backend (Development)
- **Framework**: FastAPI + Python 3.11+
- **AI Framework**: LangGraph 0.2.0
- **Status**: Skeleton implementation, most nodes are TODO

## 8-Agent Architecture (Frontend)

### Main Orchestrator
- **MainQAWorkflow** (`/frontend/src/mastra/workflows/main-qa-workflow.ts`): Central coordinator

### Specialized Agents (`/frontend/src/mastra/agents/`)

| Agent | File | Purpose |
|-------|------|---------|
| RouterAgent | `router-agent.ts` | Query classification and routing |
| BusinessInfoAgent | `business-info-agent.ts` | Hours, pricing, location (Enhanced RAG) |
| FacilityAgent | `facility-agent.ts` | Equipment, Wi-Fi, basement facilities (Enhanced RAG) |
| MemoryAgent | `memory-agent.ts` | Conversation history recall |
| EventAgent | `event-agent.ts` | Calendar and events |
| GeneralKnowledgeAgent | `general-knowledge-agent.ts` | Out-of-scope queries (web search) |
| ClarificationAgent | `clarification-agent.ts` | Ambiguity resolution |
| RealtimeAgent | `realtime-agent.ts` | Voice interaction processing |

### Supporting Agents
- **WelcomeAgent**: Initial greeting and language detection
- **SlideNarrator**: Presentation narration
- **VoiceOutputAgent**: Text-to-speech conversion
- **CharacterControlAgent**: VRM character animation

## Core Systems

### Enhanced RAG System
- **Location**: `/frontend/src/mastra/tools/enhanced-rag-search.ts`
- **Features**:
  - Entity-aware search (Engineer Cafe vs Saino vs Meeting Room)
  - RAGPriorityScorer with multi-factor scoring
  - Cross-language search (JA/EN)
  - Category-based prioritization (hours, pricing, facilities)

### Memory System (SimplifiedMemorySystem)
- **Location**: `/frontend/src/lib/simplified-memory.ts`
- **Features**:
  - 3-minute TTL conversation context
  - Agent namespace isolation
  - Request type inheritance for follow-ups
  - Emotion tracking

### Audio System
- **Location**: `/frontend/src/lib/audio/`
- **Components**:
  - AudioPlaybackService: Unified playback with lip-sync
  - MobileAudioService: Tablet/iOS compatibility
  - WebAudioPlayer: Web Audio API core
  - AudioInteractionManager: Autoplay policy handling

### Lip-sync System
- **Location**: `/frontend/src/lib/lip-sync-*.ts`
- **Features**:
  - Real-time mouth shape generation
  - Dual-layer caching (memory + localStorage)
  - Mobile-optimized performance

### STT Correction System
- **Location**: `/frontend/src/lib/stt-correction.ts`
- **Purpose**: Fix Google Cloud STT misrecognitions for Japanese terms
- **Patterns**: 19 correction groups (エンジニアカフェ, Wi-Fi, 地下, etc.)

## Key API Endpoints (Frontend)

### Voice Processing
- `POST /api/voice`: Multi-action voice endpoint (STT, TTS, processing)
- `GET /api/voice`: Status and supported languages

### Q&A System
- `POST /api/qa`: Question processing via agent orchestration
- `GET /api/qa`: Categories and sample questions

### Character & Slides
- `POST /api/character`: VRM character control
- `POST /api/slides`: Slide navigation with narration
- `POST /api/marp`: Marp markdown rendering

### Admin & Monitoring
- `/admin/knowledge`: Knowledge base management UI
- `GET /api/monitoring/dashboard`: Real-time metrics
- `POST /api/alerts/webhook`: Production alerts
- `GET /api/cron/update-knowledge-base`: Auto-sync (6-hour interval)

## Database Schema

### Core Tables (Supabase)
- `knowledge_base`: RAG content with 1536D embeddings
- `agent_memory`: Key-value with TTL for conversation memory
- `conversation_sessions`: Visitor sessions
- `conversation_history`: Chat messages

### Monitoring Tables
- `rag_search_metrics`: Search performance
- `external_api_metrics`: External API usage
- `production_alerts`: Alert history

## Development Commands

```bash
# Root level
pnpm dev              # Start both frontend and backend
pnpm dev:frontend     # Start frontend only (http://localhost:3000)
pnpm dev:backend      # Start backend only (http://localhost:8000)

# Frontend level (cd frontend)
pnpm dev              # Development server
pnpm build            # Production build
pnpm lint             # ESLint
pnpm typecheck        # TypeScript check
pnpm seed:knowledge   # Seed knowledge base
pnpm migrate:embeddings # Migrate to OpenAI embeddings
```

## Environment Variables

### Required
- `GOOGLE_CLOUD_PROJECT_ID`: GCP project
- `GOOGLE_GENERATIVE_AI_API_KEY`: Gemini API
- `OPENAI_API_KEY`: Embeddings
- `NEXT_PUBLIC_SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`: Database

### Optional
- `CRON_SECRET`: CRON job authentication
- `ALERT_WEBHOOK_SECRET`: Alert webhook auth
- `GOOGLE_CALENDAR_ICAL_URL`: Public calendar

## LangGraph Migration Plan

現在のMastra (TypeScript) 実装からLangGraph (Python) への移行を計画中です。

### 移行ドキュメント
- **詳細**: `langgraph-migration.md` メモリファイル参照
- **各エージェント仕様**: `docs/migration/agents/` ディレクトリ

### エージェント担当者
| エージェント | 担当者 | ステータス |
|-------------|--------|-----------|
| RouterAgent | テリスケ | 既存あり |
| BusinessInfoAgent | テリスケ | 既存あり |
| FacilityAgent | Natsumi | 既存あり |
| MemoryAgent | takegg0311 | 既存あり |
| EventAgent | テリスケ | 既存あり |
| ClarificationAgent | Chie | 既存あり |
| VoiceAgent | Chie | 既存あり |
| CharacterControlAgent | takegg0311 | 既存あり |
| SlideAgent | テリスケ | 既存あり |
| **OCRAgent** | **けいてぃー** | **新規** |

### OCRAgent (新機能)
- Mastra実装なし、LangGraphで新規実装
- 機能: 番号認識、テキストOCR、表情認識
- 担当: けいてぃー (メイン), たけがわ (サポート)

## Known Limitations

### Mobile/iOS
- AudioContext requires user interaction
- Lip-sync may fail on iPad
- Graceful degradation implemented

### Backend Status
- LangGraph workflow skeleton exists
- All agent nodes are TODO placeholders
- Frontend Mastra agents are the production implementation

## Performance Metrics

- **Routing Accuracy**: 94.1%
- **RAG Success**: 85%+
- **Average Response**: 2.9s
- **Conversation Window**: 3 minutes

## Important Notes

1. **Tailwind CSS**: Must use v3.4.17, NOT v4 (breaking changes)
2. **Frontend vs Backend**: Frontend Mastra is production; backend LangGraph is WIP
3. **Embeddings**: OpenAI 1536D, not Google 768D
4. **Memory TTL**: 3-minute conversation context
5. **STT Corrections**: Auto-applied for Japanese terms

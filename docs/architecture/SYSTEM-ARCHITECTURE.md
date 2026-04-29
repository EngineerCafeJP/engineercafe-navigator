# System Architecture

## Overview

Engineer Cafe Navigator is a multilingual AI navigation system for the Engineer Cafe facility in Fukuoka's Aka-Renga Cultural Center.

> Status note: Alpha Phase 4 の会話 UX / fast response については
> [ADR 018](../adr/018-alpha-fast-response-and-assistant-profile-routing.md) を優先する。

## Architecture Layers

### 1. Frontend Layer
- **Framework**: Next.js 15.3.2 with App Router
- **UI**: React 19.1.0 + TypeScript 5.8.3
- **3D Avatar**: Three.js with VRM support
- **Audio**: Web Audio API with mobile compatibility

### 2. Backend AI Agent Layer (Python)
- **Framework**: LangGraph 1.0.8 (StateGraph with Supervisor Pattern)
- **API**: FastAPI with async/await support
- **LLM Provider**: OpenRouter API plus optional native fast providers (Gemini / Cerebras) behind env flags
- **Embedding Model**: OpenAI text-embedding-3-small (1536 dims) via Supabase
- **Orchestration**: OrchestratorAgent (Supervisor Pattern with LLM dynamic routing)
- **Checkpointer**: LangGraph AsyncPostgresSaver (PostgreSQL-based state management)
- **RetryPolicy**: Applied to all LLM-dependent nodes (max_attempts=3)
- **Streaming**: astream() method for future SSE support
- **Error Handling**: Custom exception hierarchy (AgentSystemError → RoutingError, LLMGenerationError, RAGSearchError, etc.)
- **Logging**: Structured logging with exc_info=True on all error paths

### 3. Data Layer
- **Database**: PostgreSQL with pgvector (via Supabase)
- **Checkpointer**: LangGraph AsyncPostgresSaver for conversation state
- **Vector Search**: 1536-dimensional embeddings with cosine similarity
- **RAG Strategy**: Section chunking, parent context expansion, category-specific strategies, adaptive thresholds
- **Memory**: 3-minute conversation context window

### 4. Integration Layer
- **Calendar**: Google Calendar (public ICS feed) + Connpass API v2 (Fukuoka events)
- **Web Search**: Tavily API and provider-specific grounding only for current-info intents
- **Voice TTS**: PiperPlus / VoiceVox / Google Cloud fallback depending on deploy env
- **Voice STT**: Qwen primary / Vosk / Google Cloud fallback depending on deploy env
- **OCR**: OCR processing capabilities

## Key Components

### Enhanced RAG System
- **Knowledge Base**: YAML-based with schema validation, bilingual (JA/EN)
- **Embedding**: OpenAI text-embedding-3-small (1536 dims)
- **Search Strategy**:
  - Section chunking (title + section pairs)
  - Parent context expansion (category-wide context retrieval)
  - Category-specific strategies (business_hours, facilities, pricing, etc.)
  - Adaptive similarity thresholds (0.35-0.70 depending on category)
  - Context priority (context_weight: 0.85 for knowledge + 0.15 for conversation)
- **Categories**: Facilities, Business Hours, Pricing, Access, Basement, etc.

### LangGraph State Management
- **Checkpointer**: AsyncPostgresSaver (PostgreSQL-based)
- **Thread Management**: Conversation threads with automatic state persistence
- **Context Window**: 3-minute conversation memory
- **State Schema**: ConversationState (messages, context, query, intermediate_steps, current_agent)

### Agent Architecture (7 Workflow Agents + Support Agents)

**Workflow Agents** (LangGraph nodes with Supervisor Pattern routing):
1. **OrchestratorAgent**: Supervisor Pattern with LLM-based dynamic routing (RouterAgent統合済み)
2. **BusinessInfoAgent**: Business hours, pricing, access, consultation, community (Enhanced RAG)
3. **FacilityAgent**: Facilities, equipment, basement, nearby, lost & found (Enhanced RAG)
4. **EventAgent**: Google Calendar ICS + Connpass API v2
5. **SlideAgent**: Slide display and narration
6. **GeneralKnowledgeAgent**: Web search + memory queries (MemoryAgent統合済み)
7. **FarewellAgent**: Departure flow with card return reminder and brand message

**Support Agents** (not LangGraph nodes):
- **VoiceAgent**: TTS (VoiceVox local / Google Cloud)
- **CharacterControlAgent**: VRM character control
- **OCRAgent** (VisionAgent): OCR processing

**Deprecated/Merged**:
- ~~RouterAgent~~: Merged into OrchestratorAgent
- ~~ClarificationAgent~~: Absorbed into orchestrator inline processing
- ~~MemoryAgent~~: Merged into GeneralKnowledgeAgent

## 📊 Data Flow

### Standard Chat Flow

```
User Query → Frontend → FastAPI Backend (Python)
    ↓
OrchestratorAgent (LLM-based Supervisor Pattern routing)
  [Reception gate: checks if session has active reception before LLM routing]
    ↓
[Route to Appropriate Specialized Agent]
    ├─→ BusinessInfoAgent (Enhanced RAG: hours, pricing, consultation, community)
    ├─→ FacilityAgent (Enhanced RAG: equipment, nearby, lost & found, parking)
    ├─→ EventAgent (Google Calendar ICS + Connpass API v2)
    ├─→ GeneralKnowledgeAgent (Web search: Tavily + memory queries)
    ├─→ SlideAgent (Marp slide presentation + narration)
    └─→ FarewellAgent (Departure flow: card return, belongings check)
    ↓
Response Generation (OpenRouter LLM)
    ↓
Frontend (Avatar + TTS + UI)
```

### Reception Flow

```
Sensor/Button → Welcome Screen (3 buttons: member card / handwriting / voice)
    ↓
[Member card or handwriting path]
    ↓
POST /api/ocr → backend/api/ocr.py → OCRAgent → visitor_identity
    ↓
POST /api/reception/start (visitor_identity optional)
    ↓
Reception Workflow (purpose identification, visitor classification)
    ├─→ Tour → Guided slide presentation (SlideAgent)
    ├─→ Event → Event info + check-in (EventAgent)
    ├─→ Coworking → Seat availability + registration (FacilityAgent)
    └─→ General → Handoff to main chat (GeneralKnowledgeAgent)
    ↓
POST /api/reception/complete → ainvoke_from_reception() → Main Workflow
    ↓
OrchestratorAgent routes with visitor context
    ↓
Frontend (Avatar + TTS + UI)
```

Device integration (M5Stack, physical sensors) sends events to `frontend/src/lib/api/device-webhook.ts`, which triggers the Welcome screen.

### Query Processing Pipeline (LangGraph)
1. **STT Processing**: Speech recognition with STT corrections (Vosk local / Google Cloud)
2. **Language Detection**: Japanese/English with multi-language support
3. **OrchestratorAgent** (Supervisor Pattern):
   - LLM-based dynamic routing decision
   - Ambiguity detection (route to ClarificationAgent if needed)
   - Request type extraction (hours, pricing, facilities, events, etc.)
   - Context-aware routing (conversation history + user intent)
   - Automatic retry on LLM failures (RetryPolicy: max_attempts=3)
4. **Specialized Agent Processing**:
   - **Enhanced RAG** (BusinessInfo/FacilityAgent):
     - Section chunking (title + section pairs)
     - Parent context expansion (category-wide context)
     - Adaptive similarity thresholds (0.35-0.70)
     - Context priority weighting (knowledge: 0.85, conversation: 0.15)
   - **External API Integration** (EventAgent):
     - Google Calendar ICS feed parsing
     - Connpass API v2 for Fukuoka events
   - **Fast General / Identity** (GeneralKnowledgeAgent):
     - assistant profile / help / capability は deterministic response
     - daily conversation / general light は fast LLM、search なし
     - current-info intent のみ Tavily / calendar / provider grounding を使用
   - **Clarification Dialog** (ClarificationAgent):
     - Context-aware disambiguation
     - Multi-turn conversation support
5. **Response Generation**: deterministic fast path, fast LLM, or domain-specific OpenRouter LLM
6. **TTS Synthesis**: PiperPlus / VoiceVox / Google Cloud fallback
7. **Character Animation**: VRM avatar sync with lip-sync

## Critical Features

### Multi-language Support
- Japanese and English UI
- Cross-language RAG search
- STT corrections for Japanese technical terms
- Bilingual knowledge base (YAML-based)

### Contextual Understanding
- LangGraph AsyncPostgresSaver for conversation state persistence
- Context priority weighting (knowledge: 0.85, conversation: 0.15)
- Memory-aware responses (3-minute conversation window)
- Request type tracking across turns
- Ambiguity resolution with ClarificationAgent

### Alpha Fast Response Contract

ADR 018 adds a strict contract for kiosk UX:

- `あなたの名前は`, `あなたは誰`, `何ができますか`, `help` は LLM / RAG / web search に渡さない。
- rank graph に入らないだけで Tavily / web search に落とさない。
- `daily_conversation` と `general_light` は lightweight model を使うが、model id は env と benchmark で決める。
- `current_info` だけが calendar / web search を使う。
- previous `request_type` は context として扱い、current turn の high-confidence intent なしに route を固定しない。

### 12-Agent Architecture Details

#### OrchestratorAgent (Supervisor Pattern)
- LLM-based dynamic routing (replaces rule-based RouterAgent)
- Central orchestration with StateGraph
- Session management and context propagation
- Unified error handling with custom exception hierarchy
- Automatic retry on LLM failures (RetryPolicy: max_attempts=3)

#### Specialized Agent Responsibilities
1. **OrchestratorAgent**: LLM-based Supervisor Pattern routing
2. **BusinessInfoAgent**: Engineer Cafe operational information with Enhanced RAG (section chunking, parent context)
3. **FacilityAgent**: Physical facilities and equipment queries with basement focus (category-specific strategies)
4. **EventAgent**: Real-time calendar integration (Google Calendar ICS + Connpass API v2)
5. **SlideAgent**: Slide display and narration
6. **GeneralKnowledgeAgent**: assistant profile / daily conversation / general light / current-info search + memory queries (MemoryAgent統合済み)
7. **ClarificationAgent**: Context-aware ambiguity resolution
8. **VoiceAgent**: TTS (VoiceVox local / Google Cloud fallback)
9. **STTAgent**: STT (Vosk local / Google Cloud fallback)
10. **CharacterControlAgent**: VRM character control
11. **OCRAgent**: OCR processing
12. **MemoryAgent**: DEPRECATED (functionality merged into GeneralKnowledgeAgent)

### Enhanced RAG Features
- **Section Chunking**: Title + section pairs for precise retrieval
- **Parent Context Expansion**: Category-wide context retrieval
- **Adaptive Thresholds**: 0.35-0.70 similarity thresholds (category-specific)
- **Context Priority**: Knowledge (0.85) + Conversation (0.15) weighted merging
- **Category-Specific Strategies**: Business hours, facilities, pricing, access, etc.

### Integration Features
- **Google Calendar**: Public ICS feed parsing
- **Connpass API v2**: Fukuoka event listings
- **Web Search**: Tavily / provider grounding only for current-info route
- **Voice Services**: PiperPlus / VoiceVox / Qwen / Vosk / Google Cloud depending on deploy env
- **Fast LLM**: Gemini Flash-Lite candidates and Cerebras `gpt-oss-120b` behind env-gated resolver
- **LangGraph Checkpointer**: PostgreSQL-based state persistence

### Quality Assurance
- **RAGAS Evaluation Pipeline**: Faithfulness, answer correctness, context relevance
- **CI/CD Integration**: Automated evaluation on every commit
- **Test Suite**: 1166 tests (unit, integration, evaluation, RAGAS)

## 🔧 Configuration

### Environment Variables
```env
# Primary AI Provider
OPENROUTER_API_KEY=           # Required - unified LLM access (Gemini, GPT, Claude, etc.)

# Database (Supabase)
SUPABASE_URL=                 # PostgreSQL with pgvector
SUPABASE_KEY=                 # Service role key
SUPABASE_DB_URI=              # LangGraph AsyncPostgresSaver checkpointer

# Optional AI Services
OPENAI_API_KEY=               # Embeddings (text-embedding-3-small) & RAGAS evaluation
GOOGLE_API_KEY=               # Gemini grounding search (fallback)
CEREBRAS_API_KEY=             # Cerebras fast response / filler, if enabled
FAST_LLM_ENABLED=             # Enable daily/general light fast route
FAST_LLM_PRIMARY_PROVIDER=    # gemini / openrouter / cerebras
FAST_LLM_PRIMARY_MODEL=       # Verified model id only
FAST_LLM_FALLBACK_PROVIDER=   # fallback provider
FAST_LLM_FALLBACK_MODEL=      # fallback model
FAST_LLM_TERTIARY_PROVIDER=   # cerebras, if enabled
CEREBRAS_ENABLED=             # Enable Cerebras tertiary fallback / filler
CEREBRAS_FAST_MODEL=          # gpt-oss-120b candidate
CEREBRAS_REASONING_EFFORT=    # low for alpha fast path

# External Integrations
GOOGLE_CALENDAR_ICAL_URL=     # Public calendar ICS feed
CONNPASS_API_KEY=             # Connpass API v2 for Fukuoka events
TAVILY_API_KEY=               # Tavily web search (fallback)

# Voice Services (Local + Cloud Fallback)
# VoiceVox: Local Docker (primary TTS)
# Vosk: Local (primary STT)
GOOGLE_CLOUD_PROJECT_ID=      # Google Cloud fallback for TTS/STT
```

### Key Endpoints (FastAPI Backend)
- `/api/chat` - Main Q&A interactions (LangGraph StateGraph)
- `/api/voice/tts` - Text-to-Speech (VoiceVox / Google Cloud)
- `/api/voice/stt` - Speech-to-Text (Vosk / Google Cloud)
- `/api/calendar/events` - Calendar events (Google Calendar + Connpass)
- `/admin/knowledge` - Knowledge base management (YAML)

## 📈 Performance

### Optimization Strategies
- **LangGraph Checkpointer**: PostgreSQL-based state persistence (AsyncPostgresSaver)
- **Embedding Caching**: Cached similarity searches in Supabase
- **Adaptive Thresholds**: Category-specific similarity thresholds (0.35-0.70)
- **Context Priority**: Weighted merging (knowledge: 0.85, conversation: 0.15)
- **Voice Provider Selection**: PiperPlus / VoiceVox / Qwen / Vosk / Google Cloud are selected by deploy env
- **RetryPolicy**: Automatic retry on LLM failures (max_attempts=3)
- **Structured Logging**: exc_info=True on all error paths for debugging

### Monitoring
- **RAG Metrics**: Section chunking effectiveness, parent context expansion impact
- **RAGAS Evaluation**: Faithfulness, answer correctness, context relevance (CI/CD pipeline)
- **LLM Usage**: OpenRouter / Gemini / Cerebras call patterns, retry rates, fallback source
- **External API**: Google Calendar ICS, Connpass API v2, Tavily web search
- **Voice Services**: STT / chat / TTS section latency and provider usage

## 🧪 Testing

### Test Suite (1166 Tests)
- **Unit Tests**: Individual agent logic, RAG strategies, utilities
- **Integration Tests**: LangGraph StateGraph, FastAPI endpoints, database operations
- **Evaluation Tests**: RAGAS pipeline (faithfulness, answer correctness, context relevance)
- **End-to-End Tests**: Full conversation flows with LangGraph checkpointer

### RAGAS Evaluation Pipeline
- **Metrics**: Faithfulness, Answer Correctness, Context Precision, Context Recall
- **Dataset**: 13 evaluation scenarios (business hours, facilities, events, etc.)
- **LLM**: GPT-4 / GPT-5.2 for evaluation
- **CI/CD**: Automated evaluation on every commit

## 🚀 Deployment

### Production Requirements
- **Frontend**: Node.js 20+ (Next.js 15)
- **Backend**: Python 3.11+ (FastAPI + LangGraph)
- **Database**: PostgreSQL 15+ with pgvector extension
- **Voice Services**: PiperPlus / VoiceVox / Qwen / Vosk / Google Cloud depending on deploy env
- **RAM**: 4GB+ recommended (LangGraph + local voice models)
- **HTTPS**: Required for audio APIs

### Health Checks
- `/api/health` - System status (FastAPI)
- `/api/health/database` - PostgreSQL + pgvector connectivity
- `/api/health/agents` - LangGraph StateGraph status
- `/api/monitoring/ragas` - RAGAS evaluation metrics

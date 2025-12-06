# Engineer Cafe Navigator - Detailed Architecture

## Agent Query Processing Flow

```
User Voice/Text Input
    ↓
[STT + STT Corrections (Japanese)]
    ↓
[RealtimeAgent] - Voice interaction handling
    ↓
[MainQAWorkflow.processQuestion()]
    ↓
[RouterAgent] - Language detection + Query classification
    ├─ Memory-related? → [MemoryAgent]
    ├─ Business info (hours/price/location)? → [BusinessInfoAgent] + Enhanced RAG
    ├─ Facilities (wifi/equipment/basement)? → [FacilityAgent] + Enhanced RAG
    ├─ Events (calendar/workshop)? → [EventAgent] + Calendar API
    ├─ Ambiguous (cafe vs saino)? → [ClarificationAgent]
    └─ General/Unknown → [GeneralKnowledgeAgent] + Web Search
    ↓
[SimplifiedMemorySystem] - Store conversation with metadata
    ↓
[UnifiedAgentResponse] - Format with emotion, confidence, sources
    ↓
[VoiceOutputAgent] - TTS with emotion parameters
    ↓
[CharacterControlAgent] - VRM expression + animation
    ↓
Audio playback with synchronized lip-sync
```

## Enhanced RAG System Details

### RAGPriorityScorer Scoring Algorithm

```typescript
Priority Score = 
  similarity * 0.3 +     // Vector similarity
  entityMatch * 0.3 +    // Entity relevance (engineer-cafe/saino/meeting-room)
  contextMatch * 0.2 +   // Keyword matching
  practical * 0.1 +      // Actionable information
  specificity * 0.1      // Time/price/location specificity
```

### Entity Priority Order by Category
- **Pricing**: engineer-cafe > saino > meeting-room > general
- **Hours**: engineer-cafe > saino > general > meeting-room
- **Facility-info**: engineer-cafe > general > meeting-room > saino
- **Booking**: meeting-room > engineer-cafe > general > saino

### Cross-language Search Flow
1. Generate query embedding (OpenAI 1536D)
2. Search both JA and EN content
3. Deduplicate by category/subcategory
4. Apply entity-aware priority scoring
5. Return top results with practical advice

## Memory System Architecture

### SimplifiedMemorySystem Storage
```typescript
agent_memory table:
- agent_name: string (namespace isolation)
- key: "message_{timestamp}"
- value: {
    role: 'user' | 'assistant',
    content: string,
    timestamp: number,
    emotion?: string,
    sessionId?: string,
    requestType?: 'hours' | 'price' | 'location' | 'facility' | ...
  }
- expires_at: timestamp (now + 180s)
```

### Request Type Detection Patterns
- **Hours**: 営業時間|hours|何時|いつまで|when|open|close
- **Price**: 料金|cost|price|いくら|how much
- **Location**: どこ|where|場所|住所|address|アクセス
- **Facility**: 設備|facility|equipment|何がある

### Context Inheritance
Short queries like "土曜日は？" (What about Saturday?) inherit the previous requestType (e.g., "hours") for contextual responses.

## Audio System Architecture

### Web Audio API Pipeline
```
Base64 Audio Data
    ↓
AudioDataProcessor.base64ToBlob()
    ↓
WebAudioPlayer.loadAudioData()
    ↓
AudioContext → GainNode → AudioBufferSourceNode
    ↓
LipSyncAnalyzer.analyzeLipSync() [parallel]
    ↓
Playback with real-time viseme updates
```

### Mobile Compatibility Layers
1. **AudioInteractionManager**: Detect user gesture for autoplay policy
2. **MobileAudioService**: Device-specific optimizations (iPad reset handling)
3. **WebAudioPlayer**: webkitAudioContext fallback for Safari

### Lip-sync Caching Strategy
- **Memory Cache**: Map-based, 100 entries max, instant retrieval
- **localStorage Cache**: 10MB limit, 7-day expiration, persists across sessions
- **Audio Fingerprinting**: FileSize + SamplePoints + Checksum

## Voice Processing Pipeline

### Google Cloud Voice Integration
```typescript
// STT Flow
AudioBuffer → Base64 → /api/voice (action: speech_to_text)
    → GoogleCloudVoiceSimple.transcribe()
    → Apply STTCorrection patterns
    → Return: { transcript, confidence }

// TTS Flow
Text + Emotion → /api/voice (action: text_to_speech)
    → GoogleCloudVoiceSimple.synthesize()
    → Emotion-based voice parameters (speed, pitch, volume)
    → Return: { audioData: base64 }
```

### Emotion Voice Mapping (Japanese)
- **excited**: 1.43x speed, pitch +0.3, volume +2.0
- **sad**: 1.17x speed, pitch -0.5
- **angry**: 1.37x speed, pitch +0.2
- **calm**: 1.24x speed, pitch -0.2
- **happy**: 1.3x speed (baseline)

## Key File Locations

### Agent System
- `/frontend/src/mastra/index.ts` - EngineerCafeNavigator main class
- `/frontend/src/mastra/workflows/main-qa-workflow.ts` - Agent orchestration
- `/frontend/src/mastra/agents/*.ts` - Individual agent implementations
- `/frontend/src/mastra/tools/*.ts` - RAG, calendar, web search tools

### Core Libraries
- `/frontend/src/lib/simplified-memory.ts` - Memory system
- `/frontend/src/lib/audio/*.ts` - Audio services
- `/frontend/src/lib/lip-sync-*.ts` - Lip-sync analysis and caching
- `/frontend/src/lib/stt-correction.ts` - STT corrections
- `/frontend/src/lib/supabase.ts` - Database client

### API Routes
- `/frontend/src/app/api/voice/route.ts` - Voice processing
- `/frontend/src/app/api/qa/route.ts` - Q&A endpoint
- `/frontend/src/app/api/knowledge/search/route.ts` - RAG search
- `/frontend/src/app/api/monitoring/dashboard/route.ts` - Metrics

### Frontend Components
- `/frontend/src/app/page.tsx` - Main application
- `/frontend/src/app/components/VoiceInterface.tsx` - Voice UI
- `/frontend/src/app/components/CharacterAvatar.tsx` - VRM character
- `/frontend/src/app/components/MarpViewer.tsx` - Slide viewer

## Database RPC Functions

### search_knowledge_base
- Input: query_embedding (1536D), similarity_threshold, match_count
- Returns: Ranked results with similarity scores

### update_message_index_atomic
- Atomic memory index management
- Prevents race conditions in concurrent access

## LangGraph Migration Documentation

### ドキュメント構成
各エージェントの移行ドキュメントは `docs/migration/agents/` に配置:

```
docs/migration/agents/
├── router-agent/           # 4ファイル (README, SPEC, MIGRATION-GUIDE, TESTING)
├── business-info-agent/    # README.md
├── facility-agent/         # README.md
├── event-agent/           # README.md
├── memory-agent/          # README.md
├── clarification-agent/   # README.md
├── language-classifier/   # README.md
├── general-knowledge-agent/ # README.md
├── character-control-agent/ # README.md
├── voice-agent/           # README.md
├── slide-agent/           # README.md
└── ocr-agent/             # README.md (NEW - Mastra実装なし)
```

### 各READMEの構成
1. **概要**: エージェントの役割説明
2. **担当者**: メイン担当者とサポーター
3. **責任範囲**: 主要責務と範囲外
4. **アーキテクチャ上の位置づけ**: フロー図
5. **現在の実装 (Mastra)**: ファイル場所、主要メソッド
6. **LangGraph移行後の設計**: Python ノード定義
7. **テストケース概要**: テストシナリオ
8. **担当者向けチェックリスト**: 実装チェック項目

### 詳細情報
→ `langgraph-migration.md` メモリファイル参照

## Monitoring & Alerts

### Dashboard Metrics
- Total searches, avg response time
- Cache hit rates, error rates
- P50/P95/P99 percentile latencies
- Active alerts with severity

### Alert Thresholds
- Response time: 800ms (warning), 1000ms (critical)
- Error rate: 5% (warning), 10% (critical)
- Cache hit: 50% (warning)

### Automated Actions
- Critical error rate → Emergency shutdown
- Critical response time → Disable new features
- Low cache hit → Send notification

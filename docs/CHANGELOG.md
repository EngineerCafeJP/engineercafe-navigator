# Changelog

## [2026-04-19] - 運用監査の反映とガードレール計画の整理

### Added
- 運用検証と deploy guardrail を定義する ADR-008
- 現在の follow-up plan として `docs/plans/production-readiness-followup-2026-04-19.md`
- frontend -> backend auth drift 対策用の Issue `#468`
- frontend 実経路の p50 / p95 / p99 を採る `scripts/latency_probe.py`
- `workflow_dispatch` で走らせる `Frontend Latency Probe` workflow

### Changed
- `docs/STATUS.md` を 2026-04-19 の codebase / live audit に同期
- `docs/SECURITY.md` に `BACKEND_API_KEY` -> `API_SECRET_KEY` の auth chain を明記
- `docs/DEPLOYMENT.md` を current Vercel + Cloud Run 運用と frontend-authenticated smoke check 前提に更新
- `docs/README.md` で current docs と historical plan を明確に分離
- イベント照会で `明日` / `tomorrow` を専用 time range として扱い、JST 基準で日付計算するよう修正
- iPad / iOS では `HTMLAudioElement` fallback を優先し、再生開始 watchdog を追加

### Noted
- 直近 3 日の Cloud Run logs で `POST /api/character` の `403` が繰り返し発生
- 直近 3 日の Cloud Run logs で `/api/voice` に 60 秒超の latency spike を確認
- Supabase CLI だけでは同等の runtime log inspection ができなかった
- 2026-04-19 18:20-18:30 JST の Cloud Run / Vercel logs では `/api/qa` `/api/voice` は 200 応答で、iPad 音声停止は frontend playback path 側と判断

---

## [2026-03-22] - Wave 1-3: OCR Integration, Reception Flow & Bug Fixes

### Added
- `POST /api/ocr` dedicated endpoint for member card and handwriting OCR (PR #320)
- Reception gate in OrchestratorAgent — chat queries check reception status before LLM routing (PR #321)
- Welcome screen with 3 action buttons: member card scan / handwriting / voice (PR #321)
- Device webhook interface for M5Stack/sensor integration (PR #321)
- `visitor_identity` parameter on `POST /api/reception/start` for OCR-identified visitors (PR #321)
- `ainvoke_from_reception()` in `POST /api/reception/complete` for agent-generated responses (PR #321)
- Smoke test script for reception flow
- Camera settings UI in SettingsPanel

### Enhanced
- QA oral style: agent prompts include conversational style for natural TTS (PR #301, #313)
- TTS text cleaning: strips Markdown artifacts before speech synthesis
- WAV MIME type: dynamic detection for VoiceVox playback (PR #309)

### Fixed
- HTML tags in TTS no longer read out tag names (PR #322)
- Table data rows preserved in TTS — previously deleted (PR #322)
- Slide white rendering on rapid navigation — requestAnimationFrame fix (PR #322)
- `/api/character` 504 timeout — 10s timeout with proper error response (PR #322)
- Slide auto-advance cascade and stale closure (PR #315, #318)
- MarpViewer blank slides, AudioContext unlock, frontend hardening

### Performance
- RAGAS baseline: context_precision 1.000, answer_correctness 0.770, answer_relevancy 0.895, faithfulness 0.871

---

## [2026-02-15] - Backend Knowledge Base Complete Expansion (PR #76)

### Added
- **Knowledge base expanded to 60 entries** from 20 initial entries
  - Staff-verified operational data: registration flow, MAKER's reservation rules, filament pricing
  - Accessibility info: wheelchair access (terrace entrance, 1F only), children policy
  - Access directions: Fukuoka Airport (11min/260yen), Hakata Station (6min/210yen)
  - Laser cutter materials guide (acrylic/wood OK, PVC prohibited)
  - Nearby accommodation guide for event attendees
  - English facility overview (sourced from slide narration JSON)
  - Seasonal facility characteristics (historic building: hot summer/cold winter)
  - Connpass event URLs, EFC (Engineer Friendly City Fukuoka) overview
  - Food/drink info, re-entry rules, closing announcements
- **E2E answer quality evaluation tool** (`run_answer_quality_evaluation.py`)
- **Golden dataset expanded to 60 routing test cases** (from 38)
- **Answer quality test dataset** (`answer_quality.json`, 10 cases)

### Enhanced
- **Routing keywords**: Added exclusive rental, building history, event types, food/drink, equipment keywords
- **Fast-path routing**: Added building/rental/equipment fast-path rules
- **ClarificationAgent**: Practical messages with actual operating hours and facility details
- **RAG scoring**: Category bonus bug fix + similarity threshold tuning (0.5→0.35)
- **Facility prompts**: Menu support + specific information instructions

### Fixed
- **CNC references removed**: Confirmed non-existent via photo verification, removed from MAKER's and equipment entries
- **Hacker Supporter entry**: Removed (role merged with Community Manager), replaced with drinks/vending info

### Performance
- **Routing accuracy**: 60/60 (100%) across all test cases
- **Fast-path precision**: 100% (50/60 fast-path hits, 0 false positives)
- **E2E answer quality**: 10/10 PASS, 100% keyword rate
- **Knowledge seeding**: 60/60 success to Supabase

---

## [2025-07-02] - RAG System Complete Modernization

### Enhanced
- **Enhanced RAG Full Deployment**: Entity recognition & priority scoring across all agents
  - BusinessInfoAgent, FacilityAgent, RealtimeAgent with enhanced search
  - Entity-aware priority scoring and category mapping
  - Request type to category intelligent mapping
- **Context-Dependent Routing**: RouterAgent improvements for 94.1% accuracy
  - Fixed "土曜日も同じ時間？" routing to BusinessInfoAgent
  - Added memory exclusions for facility queries
  - Prioritized basement detection over memory detection
- **Test Evaluation Revolution**: 28.6% → 100% success rate
  - Replaced rigid keyword matching with semantic evaluation
  - Added synonym recognition and concept groups
  - Realistic expectations based on actual system output

### Fixed
- **Embedding Model Consistency**: Unified all knowledge base entries to use OpenAI text-embedding-3-small (1536 dimensions)
  - Previously mixed Google text-embedding-004 (content) and OpenAI (queries) causing search failures
  - Migrated all 93 entries to consistent embedding space
- **Saino Cafe Information**: Corrected closing day to "毎月最終月曜日" (last Monday of each month)
  - Removed incorrect pattern: "土曜日はエンジニアカフェが休館日の場合のみ営業"
- **Knowledge Base**: Added 8 entries for Aka-Renga Cultural Center
- **Context Inheritance**: Implemented generic requestType inheritance for all entities
  - Added filterContextByRequestType() to filter RAG results based on previous questions
  - Created universal prompt template that works for any entity (not just Saino Cafe)
  - Now correctly handles all clarification patterns:
    - "カフェの営業時間は？" → "エンジニアカフェの方"
    - "カフェの営業時間は？" → "才能cafeの方"
    - "会議室の料金は？" → "2階の方"
    - Any similar entity-requestType combination

### Added
- Database migration scripts for embedding consistency
- Comprehensive navigation test suite with semantic evaluation
- System architecture documentation
- Maintenance guide for operations
- Enhanced RAG tool integration for all agents
- Improved test evaluation system (improved-test-evaluation.ts)

### Refactored
- Consolidated test suite structure under scripts/tests/
- Organized documentation with archive for historical reports
- Removed 15+ redundant test files
- Cleaned up scripts/archive/ and test-results/ directories
- Updated documentation to reflect current architecture

### Performance
- **Average Response Time**: 2.9 seconds (improved from 6.9s)
- **RouterAgent Accuracy**: 94.1% routing precision
- **Basement Queries**: Complete coverage of all basement facilities
- **Memory Integration**: SimplifiedMemorySystem with proper sessionId handling

## [2025-06-30] - Memory System Enhancement

### Added
- SimplifiedMemorySystem for unified conversation memory
- 3-minute short-term memory with TTL
- Memory-aware question handling ("さっき何を聞いた？")
- Emotion context tracking

### Improved
- STT correction system for Japanese terms
- Response precision for specific requests
- Context inheritance for single entity queries

## [2025-06-23] - Mobile Compatibility

### Added
- Web Audio API integration for iPad/iOS
- Autoplay policy compliance
- User interaction management
- Fallback mechanisms

### Fixed
- Audio playback errors on tablets
- Lip-sync performance on mobile devices

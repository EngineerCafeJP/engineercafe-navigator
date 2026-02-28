# Phase B Implementation Report

## 1. Summary

Phase B implements reception feature enhancements for Issues #103, #105, #106, #107.

| Issue | Feature | Status |
|-------|---------|--------|
| #103 | visitor_id localStorage persistence | Done |
| #105 | Emergency response templating (4 subtypes) | Done |
| #106 | Discord Webhook notification service | Done |
| #107 | Returning visitor detection (long_term_memory) | Done |

Branch: `feat/reception-phase-b` (base: `origin/develop`)

---

## 2. Changed Files

| File | Change | Issue |
|------|--------|-------|
| `backend/utils/emergency_templates.py` | NEW: 4 subtypes (earthquake/fire/medical/general) | #105 |
| `backend/services/discord_notification_service.py` | NEW: Discord Webhook notification | #106 |
| `backend/config/routing_constants.py` | ADD: EARTHQUAKE/FIRE/MEDICAL_EMERGENCY_KEYWORDS | #105 |
| `backend/workflows/main_workflow.py` | MOD: emergency inline + Discord + returning visitor | #105,#106,#107 |
| `backend/.env.example` | ADD: DISCORD_WEBHOOK_URL | #106 |
| `frontend/src/app/page.tsx` | MOD: getOrCreateVisitorId() + localStorage | #103 |
| `frontend/src/app/api/qa/route.ts` | MOD: visitor_id forwarding to backend | #103 |
| `backend/tests/utils/test_emergency_templates.py` | NEW: 35 tests | #105 |
| `backend/tests/services/test_discord_notification_service.py` | NEW: 7 tests | #106 |
| `backend/tests/workflows/test_returning_visitor.py` | NEW: 27 tests | #107 |
| `backend/tests/e2e/test_phase_b_e2e.py` | NEW: 22 E2E tests | all |
| `backend/tests/evaluation/test_ragas_phase_b.py` | NEW: 12 tests (9 integrity + 3 RAGAS) | all |
| `backend/tests/fixtures/golden_datasets/ground_truth.json` | ADD: 15 entries (gt-078 to gt-092) | all |
| `backend/log/test/PHASE_B_REPORT.md` | NEW: this report | all |

---

## 3. Unit Test Results

```
Test Suite                            | Tests | Status
--------------------------------------|-------|-------
test_emergency_templates.py           |    35 | PASS
test_discord_notification_service.py  |     7 | PASS
test_returning_visitor.py             |    27 | PASS
test_ragas_phase_b.py (integrity)     |     9 | PASS
--------------------------------------|-------|-------
Phase B Total                         |    78 | PASS
```

### Full Regression (all non-E2E/RAGAS/slow tests)

```
2181 passed, 2 skipped, 167 deselected, 0 failed (42.68s)
```

---

## 4. Lint & Format

```
ruff check backend/     -> All checks passed!
black --check backend/  -> 245 files would be left unchanged.
```

---

## 5. Feature Coverage Matrix

| Feature | Unit Test | E2E Test | Ground Truth | Status |
|---------|-----------|----------|-------------|--------|
| Emergency (earthquake) | test_emergency_templates.py | TestEmergencySubtypes | gt-078, gt-087 | Done |
| Emergency (fire) | test_emergency_templates.py | TestEmergencySubtypes | gt-079 | Done |
| Emergency (medical) | test_emergency_templates.py | TestEmergencySubtypes | gt-080 | Done |
| Emergency (general) | test_emergency_templates.py | TestEmergencySubtypes | - | Done |
| Discord notification | test_discord_notification_service.py | TestDiscordNotificationE2E | - | Done |
| Returning visitor | test_returning_visitor.py | TestReturningVisitorE2E | gt-082, gt-085 | Done |
| First-time visitor | test_returning_visitor.py | TestReturningVisitorE2E | gt-081 | Done |
| visitor_id persistence | - | TestVisitorIdPersistence | - | Done |
| Emergency routing priority | test_returning_visitor.py | TestEmergencyRoutingPriority | - | Done |
| Reception (general) | test_returning_visitor.py | - | gt-083, gt-084 | Done |
| Accessibility | - | - | gt-086 | Done |

---

## 6. Architecture Decisions

### Emergency Response: Template-based (No LLM)
- Follows `clarification_templates.py` pattern
- Pure function: `get_emergency_response(query, language) -> EmergencyResult`
- Keyword-based subtype classification: `classify_emergency_subtype(query)`
- Confidence: earthquake/fire/medical = 0.95, general = 0.85
- Emotion tag: always "serious"

### Discord Notification: Fire-and-Forget
- `asyncio.create_task()` for non-blocking notification
- Failure never propagates to user response
- Singleton pattern with `get_discord_notification_service()`
- `DISCORD_WEBHOOK_URL` env var; disabled if not set

### Returning Visitor Detection: long_term_memory
- Priority: first_time keywords > long_term_memory > general
- `long_term_memory` loaded from LangGraph Store in `_memory_loader_node`
- Cross-thread persistence via `visitor_memories` namespace

### visitor_id Persistence: localStorage
- `crypto.randomUUID()` for unique visitor ID
- SSR safe: returns 'anonymous' on server side
- Forwarded to backend via `visitor_id` field in API request

---

## 7. Trace: Input -> Output

### Emergency Flow
```
User: "地震です！"
  -> OrchestratorAgent.decide_next_agent() -> category="emergency"
  -> classify_emergency_subtype("地震です！") -> "earthquake"
  -> _EARTHQUAKE["ja"] -> template message
  -> add_emotion_tag(message, "serious") -> "[serious]地震です！..."
  -> asyncio.create_task(_notify_discord_emergency()) -> fire-and-forget
  -> Command(goto="format_response", answer=tagged_message)
```

### Returning Visitor Flow
```
User: "こんにちは" (with long_term_memory=[{data: "前回WiFi質問"}])
  -> OrchestratorAgent.decide_next_agent() -> request_type="reception"
  -> long_term_memory exists -> reception_type="returning"
  -> get_reception_response(language="ja", reception_type="returning")
  -> "おかえりなさい！エンジニアカフェへようこそ。"
```

### visitor_id Flow
```
Frontend: localStorage.getItem("engineer_cafe_visitor_id")
  -> null -> crypto.randomUUID() -> localStorage.setItem()
  -> API request body: { visitor_id: "uuid-..." }
  -> Backend: WorkflowContext(user_id="uuid-...")
  -> Store namespace: ("visitor_memories", "uuid-...")
```

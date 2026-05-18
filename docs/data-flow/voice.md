# Data Flow: `/api/voice/*`

## Client

- Browser voice calls use `speechToText()` and `textToSpeech()` in `frontend/src/lib/api/voice-client.ts:259` and `frontend/src/lib/api/voice-client.ts:283`.
- Both helpers POST JSON to `VOICE_PATH = '/api/voice'` from `frontend/src/lib/api/voice-client.ts:98`.
- `VoiceInterface` imports these helpers at `frontend/src/app/components/VoiceInterface.tsx:29`.

## API Route

- Next.js receives voice POSTs in `frontend/src/app/api/voice/route.ts:26`.
- The route validates `action`, extracts STT/TTS fields, and forwards to backend `/api/voice` at `frontend/src/app/api/voice/route.ts:77`.
- Backend proxy auth, URL construction, timeout, and JSON parsing live in `frontend/src/lib/api/backend-proxy.ts:58`.
- Voice metadata GETs proxy to backend `/api/voice` at `frontend/src/app/api/voice/route.ts:106`.

## Backend

- FastAPI handles POST `/api/voice` at `backend/main.py:1544`.
- `speech_to_text` delegates to `_handle_stt()` at `backend/main.py:1710`; `_handle_stt()` decodes base64 audio and calls `STTAgent.speech_to_text()` at `backend/main.py:1316`.
- Qwen-primary STT is implemented in `backend/agents/stt_agent.py:1534`; Vosk fallback is implemented in `backend/agents/stt_agent.py:1118`.
- `text_to_speech` creates a TTS task through `_resolve_tts_agent(body).text_to_speech()` at `backend/main.py:1555`.
- TTS provider selection and fallback are in `backend/agents/voice_agent.py:908`; synthesis orchestration is in `backend/agents/voice_agent.py:1184`.
- Static filler audio is served by backend `/api/voice/filler` at `backend/main.py:1104`.

## Response

- STT success returns `VoiceResponse` with transcript, confidence, provider, requestId, phase, and upstreamStatus at `backend/main.py:1449`.
- TTS success returns base64 audio, audio format, emotion, clean text, VRM control if requested, and upstreamStatus at `backend/main.py:1677`.
- Frontend normalizes STT and TTS response payloads in `frontend/src/lib/api/voice-client.ts:180` and `frontend/src/lib/api/voice-client.ts:199`.
- Failed backend responses are converted by `createBackendErrorResponse()` from `frontend/src/app/api/voice/route.ts:95`.

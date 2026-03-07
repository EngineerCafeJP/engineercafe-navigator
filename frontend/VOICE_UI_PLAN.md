# Voice UI Migration Plan

## Goal

Issue #116 moves the main interaction surface from button-led controls to voice-led controls while keeping buttons and text input as accessibility fallbacks. Phase 1 in this change set only adds the core hooks required for that migration and documents the rollout path.

## Current State Survey

### Active screen flow

- `src/app/page.tsx`
  - This is the active entry surface today.
  - The default experience is still button-first:
    - language selection buttons
    - first-time-user buttons
    - push-to-talk mic button
    - end conversation button
  - Voice capture is handled directly in the page through `VoiceRecorder`.
  - Recording is press-and-hold with a hard-coded 10 second auto-stop timeout.
  - There is no compact text input, no clarification chip UI, and no accessibility-first mode.

### Existing voice UI component

- `src/app/components/VoiceInterface.tsx`
  - Not imported by `page.tsx`, so it appears to be an unused or alternate voice UI surface.
  - It already contains:
    - a voice state machine (`idle`, `listening`, `processing`, `speaking`)
    - `@ricky0123/vad-react` based barge-in handling
    - waveform placeholder bars
    - auto-listen toggle
    - transcript/response display
  - It is currently a large monolithic component and exceeds the intended long-term component size target.

### Existing supporting code

- `src/lib/voice-recorder.ts`
  - Contains `VoiceRecorder` and `AdvancedVoiceRecorder`.
  - Already supports microphone initialization and basic real-time level analysis.
- `src/lib/audio/audio-interaction-manager.ts`
  - Handles mobile/browser audio unlock requirements.
- `src/lib/clarification-utils.ts`
  - Detects clarification-style responses and extracts options.
  - No UI layer currently consumes this to render tappable options.
- `src/app/components/CharacterAvatar.tsx`
  - Already maps voice-related character states such as `listening` and `speaking`.
  - This is the correct integration point for stronger animation linkage later.

### Gaps against Issue #116

- No wake-word detection path
- No session-level continuous listening controller
- No silence-based session termination
- No real waveform data connected to the main UI
- No compact collapsible text input
- No accessibility mode that foregrounds text input
- No clarification option buttons connected to response parsing
- No shared controller that coordinates wake word, VAD, waveform, silence, and character state
- No dedicated chat panel/message list abstraction under `src/app/components`

## Files To Change

### Existing files to modify in later phases

- `src/app/page.tsx`
  - Replace push-to-talk-first orchestration with a session controller that can arm wake-word mode and continuous listening.
- `src/app/components/VoiceInterface.tsx`
  - Split into smaller controller/presentation components or retire in favor of the page-level shell.
- `src/app/components/CharacterAvatar.tsx`
  - Add tighter hooks for listening/speaking/wake-word animation state.
- `src/app/globals.css`
  - Add waveform-specific visual utilities only if Tailwind utilities are insufficient.
- `src/lib/clarification-utils.ts`
  - Expand structured extraction if backend responses need more robust parsing.

### New files created in Phase 1

- `src/app/hooks/browser-speech.ts`
- `src/app/hooks/useWakeWord.ts`
- `src/app/hooks/useContinuousListening.ts`
- `src/app/hooks/useSilenceDetection.ts`
- `src/app/hooks/useVoiceWaveform.ts`

### Likely new files for later phases

- `src/app/components/voice/VoiceConversationShell.tsx`
- `src/app/components/voice/VoiceStatusBadge.tsx`
- `src/app/components/voice/VoiceWaveform.tsx`
- `src/app/components/voice/CompactTextInput.tsx`
- `src/app/components/voice/ClarificationOptions.tsx`
- `src/app/components/voice/AccessibilityModeToggle.tsx`
- `src/app/hooks/useVoiceSessionController.ts`

## Implementation Order

### Step 1: Browser voice primitives

Create browser-facing hooks that do not alter current behavior until they are explicitly wired in.

- `useWakeWord`
  - Wrap Web Speech API wake-word recognition.
  - Detect configured phrases such as `すみません` and `hello`.
  - Auto-restart recognition while idle.
- `useContinuousListening`
  - Provide a small state machine for session mode transitions.
  - Expose `shouldArmWakeWord` and `shouldListen` so UI/controller layers can decide when to open the mic.
- `useSilenceDetection`
  - Track recent speech activity.
  - Trigger a callback when no meaningful activity is detected for the configured timeout.
- `useVoiceWaveform`
  - Convert a `MediaStream` into bar data for visual feedback.
  - Keep it presentation-agnostic so both page-level UI and a future `VoiceWaveform` component can reuse it.

### Step 2: Session controller hook

Add `useVoiceSessionController` to coordinate:

- wake-word idle mode
- explicit accessibility/manual text mode
- continuous listening after AI speech ends
- silence timeout termination
- character animation state updates
- fallback button and text actions

This hook should own the high-level state machine so UI components remain presentational.

### Step 3: Main voice-led shell

Introduce a dedicated shell component that replaces the current button cluster in `page.tsx`.

- Default state:
  - large listening presence
  - waveform feedback
  - small secondary text input
  - limited fallback buttons
- Accessibility mode:
  - expanded text input
  - clear focus affordances
  - voice controls still available but de-emphasized

### Step 4: Clarification UX

When the backend returns clarification-style responses:

- parse options via `ClarificationUtils`
- render tappable clarification buttons
- submit the selected option as the next user turn
- keep text input available for custom clarification replies

### Step 5: Character linkage

Drive character behavior from shared voice/session state instead of one-off local updates.

- idle: neutral breathing
- wake-word armed: subtle attentive animation
- listening: stronger attentive pose
- processing: thinking
- speaking: lip-sync plus speaking expression
- silence timeout: return smoothly to idle

## Detailed Design Notes

### `useWakeWord`

- Browser-only, optional feature.
- Uses `SpeechRecognition` or `webkitSpeechRecognition` if present.
- Normalizes transcripts before matching.
- Returns the last transcript and matched wake word so the controller can show feedback.
- Debounces repeated matches from interim transcripts.

### `useContinuousListening`

- Does not directly access the microphone.
- Exposes a state machine with explicit transition methods:
  - `startSession`
  - `endSession`
  - `beginListening`
  - `beginProcessing`
  - `beginSpeaking`
  - `completeAssistantTurn`
- Keeps the policy separate from transport details.

### `useSilenceDetection`

- Tracks activity timestamps rather than owning audio capture.
- Can be fed by:
  - STT partial/final transcripts
  - VAD activity
  - waveform average level
- This allows the future controller to combine multiple signals without duplicating timers.

### `useVoiceWaveform`

- Accepts an existing `MediaStream`.
- Builds analyzer bars without changing the recording pipeline.
- Returns normalized bar levels and an aggregate average level.
- Safe to attach only while the stream is active.

## Phase Boundaries

### Included now

- planning document
- hook scaffolding with production TypeScript types
- zero-risk additions that do not alter the active UI flow

### Deferred intentionally

- replacement of the current page UI
- new voice shell and accessibility mode UI
- clarification buttons in the active screen
- direct integration of wake-word and silence timeout into live sessions
- package-level test tooling changes

## Validation Plan

- `pnpm tsc --noEmit`
- `pnpm biome check`

At the time of writing, the repository does not appear to include Biome or Jest/React Testing Library dependencies/configuration, so validation may require separate tooling setup before those commands can pass consistently.

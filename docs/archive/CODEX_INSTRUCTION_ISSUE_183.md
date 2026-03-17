# Codex Implementation Instruction: Issue #183
# VTuber/AITuber-style Fullscreen UI Restoration & VRM Display Fix

GitHub Issue: https://github.com/EngineerCafeJP/engineercafe-navigator/issues/183

---

## CRITICAL CONTEXT

Commit `c0aa3a7b` replaced the original 951-line AITuber-style `page.tsx` (fullscreen VRM character with overlay controls) with a 141-line dashboard-style UI. The VRM character is now broken (white screen, console errors), and the entire UI concept diverged from the product vision.

**Product Vision**: YouTube VTuber-like experience where the VRM character dominates the screen, with voice-driven interaction and minimal UI controls overlaid on the character.

---

## REFERENCE ARCHITECTURE (MANDATORY)

All three major VRM chat projects (pixiv/ChatVRM, tegnike/aituber-kit, pixiv/local-chat-vrm) use the SAME layout pattern. You MUST follow this pattern:

```
VrmViewer:  absolute top-0 left-0 w-screen h-[100svh] z-low
            canvas: h-full w-full (fullscreen 3D canvas as background)

UI Overlay: absolute/fixed z-high (all controls float OVER the character)
            bottom-0: voice/message input
            corners: settings icons (minimal)
```

### Z-Index Hierarchy (from ChatVRM)

| Z-Index | Layer | Content |
|---------|-------|---------|
| -z-10 | Background | VRM Canvas (fullscreen 3D character) |
| z-10 | Middle | Response bubble / chat overlay |
| z-20 | Foreground | Voice controls / input bar (bottom) |
| z-30 | Controls | Settings gear / corner icons |
| z-40 | Highest | Slide modal / settings panel |

### Reference: pixiv/ChatVRM VrmViewer.tsx
```tsx
<div className="absolute top-0 left-0 w-screen h-[100svh] -z-10">
  <canvas ref={canvasRef} className="h-full w-full" />
</div>
```

### Reference: tegnike/aituber-kit index.tsx
```tsx
<div className="h-[100svh] bg-cover" style={backgroundStyle}>
  <VrmViewer />       {/* absolute full screen, z-5 */}
  <Form />            {/* message input overlay */}
  <Menu />            {/* settings menu overlay */}
  <KioskOverlay />
</div>
```

### Reference: pixiv/ChatVRM MessageInput.tsx
```tsx
<div className="absolute bottom-0 z-20 w-screen">
  <div className="bg-base text-black">
    <div className="mx-auto max-w-4xl p-16">
      <div className="grid grid-flow-col gap-[8px] grid-cols-[min-content_1fr_min-content]">
        <IconButton />  {/* Microphone */}
        <input />       {/* Text input */}
        <IconButton />  {/* Send */}
      </div>
    </div>
  </div>
</div>
```

---

## CONSOLE ERRORS TO FIX (4 items)

### Error 1: face-api.js SRI Error
- **Message**: `Failed to find a valid digest in the 'integrity' attribute for resource 'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js'`
- **File**: `frontend/src/app/layout.tsx` line 38
- **Cause**: Script loaded via CDN with wrong integrity hash. face-api.js is NEVER used anywhere in the source code (confirmed by grep).
- **Fix**: DELETE line 38 entirely.

```tsx
// DELETE THIS LINE (line 38):
<script defer src="https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js" integrity="sha384-hkdWrJct7B7QgkF6qkHOd8QKEb2Kqmq3R6gOTbKhvEcxBFo8wD2EbGm9CbPZhqnW" crossOrigin="anonymous"></script>
```

### Error 2: "surprised" expression not found
- **Message**: `"surprised" expression not found in VRM model!`
- **File**: `frontend/src/app/components/CharacterAvatar.tsx`
- **Cause**: `sakura.vrm` does not have a "surprised" blendshape. Multiple code paths reference it.

**Fix locations:**

1. **Line 96** - `getSessionPoseOffsets()` function:
```tsx
// BEFORE (line 96):
expression: 'surprised',
// AFTER:
expression: 'happy',
```

2. **Lines 740-743** - Remove the console.warn:
```tsx
// DELETE these lines (740-743):
const has_surprised = available_expressions.includes('surprised');
if (!has_surprised) {
  console.warn('... "surprised" expression not found in VRM model!');
}
```

3. **Lines 1010-1023** - Fix circular expression mapping:
```tsx
// BEFORE (lines 1010-1023):
const expressionMapping: Record<string, string> = {
  'neutral': 'neutral',
  'happy': 'happy',
  'sad': 'sad',
  'angry': 'angry',
  'surprised': 'curious',  // maps to non-existent 'curious'
  'relaxed': 'relaxed',
  'thinking': 'relaxed',
  'speaking': 'happy',
  'listening': 'surprised', // maps to non-existent 'surprised'
  'greeting': 'happy',
  'explaining': 'neutral'
};

// AFTER:
const expressionMapping: Record<string, string> = {
  'neutral': 'neutral',
  'happy': 'happy',
  'sad': 'sad',
  'angry': 'angry',
  'surprised': 'happy',
  'relaxed': 'relaxed',
  'thinking': 'relaxed',
  'speaking': 'happy',
  'listening': 'happy',
  'greeting': 'happy',
  'explaining': 'neutral'
};
```

4. **Lines 792-795** - Already correct, keep as-is:
```tsx
const expressionFallbackMap: Record<string, string> = {
  'curious': 'neutral',
  'surprised': 'happy',
};
```

### Error 3: VRM 0.0 LookAtDegreeMap Warning
- **Message**: `Curves of LookAtDegreeMap defined in VRM 0.0 are not supported`
- **Cause**: `sakura.vrm` is VRM 0.0 format. This warning comes from `@pixiv/three-vrm` library internals.
- **Fix**: Cannot be fixed without converting the model. This is a KNOWN limitation. Document it but do not attempt to suppress library-internal warnings.

### Error 4: VRMLookAtQuaternionProxy Warning
- **Message**: `createVRMAnimationClip: VRMLookAtQuaternionProxy is not found. Creating a new one automatically`
- **Cause**: VRM 0.0 compatibility layer in `@pixiv/three-vrm-animation`.
- **Fix**: Same as Error 3 - library-internal, cannot suppress. Known behavior for VRM 0.0 models.

---

## FILE CHANGES

### File 1: `frontend/src/app/layout.tsx`

**Current content (46 lines):**
```tsx
import type { Metadata, Viewport } from 'next'
import { Inter, Noto_Sans_JP } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
})

const notoSansJP = Noto_Sans_JP({
  subsets: ['latin'],
  variable: '--font-noto-jp',
  weight: ['300', '400', '500', '700']
})

export const metadata: Metadata = {
  title: 'Engineer Cafe Navigator',
  description: '福岡市エンジニアカフェの音声AIエージェントシステム',
  keywords: ['エンジニアカフェ', 'Engineer Cafe', 'AI', '音声案内', 'Fukuoka'],
  authors: [{ name: 'Engineer Cafe Team' }],
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#3B82F6',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja" className={`${inter.variable} ${notoSansJP.variable}`}>
      <head>
        <link rel="icon" href="/assets/images/favicon.ico" />
        <script defer src="https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js" integrity="sha384-hkdWrJct7B7QgkF6qkHOd8QKEb2Kqmq3R6gOTbKhvEcxBFo8wD2EbGm9CbPZhqnW" crossOrigin="anonymous"></script>
      </head>
      <body className="font-sans antialiased min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
        {children}
      </body>
    </html>
  )
}
```

**Changes:**
1. DELETE line 38 (face-api.js script tag)
2. Change body className on line 40: remove `min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50` (VRM canvas covers entire screen, body bg is irrelevant)

**Target content:**
```tsx
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja" className={`${inter.variable} ${notoSansJP.variable}`}>
      <head>
        <link rel="icon" href="/assets/images/favicon.ico" />
      </head>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
```

---

### File 2: `frontend/src/app/components/CharacterAvatar.tsx`

This is a 1446-line file. Only modify these specific locations:

**Line 96**: Change `'surprised'` to `'happy'`
**Lines 740-743**: Delete the surprised check and console.warn
**Lines 1010-1023**: Fix expression mapping (see Error 2 above)

DO NOT modify any other part of this file. It handles VRM loading, Three.js rendering, animations, lip-sync, and settings panels.

---

### File 3: `frontend/src/app/page.tsx` (COMPLETE REWRITE)

**Current content** (141 lines): Dashboard-style layout with VoiceConversationShell. DELETE ALL.

**New content must follow this architecture:**

```
<main className="relative h-[100svh] w-screen overflow-hidden">

  {/* ===== Layer 0: VRM Canvas (fullscreen background) ===== */}
  <div className="absolute inset-0 -z-10">
    <CharacterAvatar
      modelPath="/characters/models/sakura.vrm"
      sessionState={sessionState}
      background={characterBackground}
      lightingIntensity={lightingIntensity}
      enableClickAnimation={!showSlideMode}
      onVisemeControl={(setViseme) => { ... }}
      onExpressionControl={(setExpression) => { ... }}
      onBackgroundChange={setCharacterBackground}
      onLightingChange={setLightingIntensity}
    />
  </div>

  {/* ===== Layer 1: Response bubble overlay ===== */}
  <div className="pointer-events-none absolute inset-x-0 top-0 z-10 ...">
    {/* Show AI response text + clarification buttons */}
    {/* Semi-transparent card, max 4 lines, positioned top-center or bottom-above-controls */}
  </div>

  {/* ===== Layer 2: Voice controls (bottom center floating) ===== */}
  <div className="absolute inset-x-0 bottom-0 z-20 ...">
    {/* Large circular mic button (center) */}
    {/* Waveform visualization bars */}
    {/* Language toggle (ja/en pills) */}
    {/* Expandable text input (optional, collapsed by default) */}
  </div>

  {/* ===== Layer 3: Corner controls (top-right) ===== */}
  <div className="absolute right-4 top-4 z-30 ...">
    {/* Presentation start button (small icon) */}
    {/* Settings already handled by CharacterAvatar internally */}
  </div>

  {/* ===== Layer 4: Slide overlay (CONDITIONAL, modal-like) ===== */}
  {showSlideMode && (
    <div className="absolute inset-0 z-40 bg-black/50 backdrop-blur-sm">
      {/* MarpViewer centered with close button */}
    </div>
  )}

</main>
```

**Critical implementation details for page.tsx:**

1. Use `VoiceInterface` component with its render-prop pattern (`children` function):
```tsx
import VoiceInterface, { type VoiceSessionState } from './components/VoiceInterface';
```
VoiceInterface provides: `sessionState`, `transcript`, `response`, `metadata`, `waveformBars`, `startListening`, `stopListening`, `sendMessage`, `currentLanguage`, `error`, `loadingMessage`, `wakeWord`, `clearConversation`

2. Wrap the entire layout inside VoiceInterface's render-prop:
```tsx
<VoiceInterface
  language={currentLanguage}
  onLanguageChange={setCurrentLanguage}
  onVisemeControl={setVisemeFunction}
  showDefaultUI={false}
>
  {(voice) => (
    <main className="relative h-[100svh] w-screen overflow-hidden">
      {/* ... layers here using voice.sessionState, voice.response, etc. */}
    </main>
  )}
</VoiceInterface>
```

3. Import and use the clarification logic from VoiceConversationShell:
```tsx
import { ClarificationUtils } from '@/lib/clarification-utils';
```
Copy the `clarificationOptionMap` and `getClarificationOptions` function into page.tsx (or a shared util).

4. Import ClarificationButtons component:
```tsx
import ClarificationButtons from './components/ClarificationButtons';
```

5. State variables needed:
```tsx
const [currentLanguage, setCurrentLanguage] = useState<'ja' | 'en'>('ja');
const [showSlideMode, setShowSlideMode] = useState(false);
const [characterBackground, setCharacterBackground] = useState<BackgroundOption>({
  id: 'engineer-cafe-bg',
  name: 'Engineer Cafe',
  type: 'image',
  value: '/backgrounds/IMG_5573.JPG',
});
const [lightingIntensity, setLightingIntensity] = useState(1);
const [setVisemeFunction, setSetVisemeFunction] = useState<((viseme: string, intensity: number) => void) | null>(null);
const [setExpressionFunction, setSetExpressionFunction] = useState<((expression: string, weight: number) => void) | null>(null);
const [textDraft, setTextDraft] = useState('');
const [showTextInput, setShowTextInput] = useState(false);
```

6. Slide mode activation:
```tsx
const startPresentation = useCallback((language: 'ja' | 'en') => {
  setCurrentLanguage(language);
  setShowSlideMode(true);
  window.setTimeout(() => {
    window.dispatchEvent(
      new CustomEvent('autoStartPresentation', {
        detail: { autoPlay: true, language },
      }),
    );
  }, 150);
}, []);
```

7. MarpViewer import and usage:
```tsx
import MarpViewer from './components/MarpViewer';
// Props: language, onVisemeControl, onExpressionControl
```

---

### File 4: `frontend/src/app/components/VoiceConversationShell.tsx`

After page.tsx is rewritten, this file will NO LONGER be imported anywhere.
- Verify with: `grep -rn "VoiceConversationShell" frontend/src/` (should only show the file itself)
- DELETE this file entirely.

---

## EXACT UI SPECIFICATIONS

### Mic Button (Bottom Center)
- Size: `w-20 h-20 md:w-24 md:h-24` (80px mobile, 96px desktop)
- Shape: `rounded-full`
- Colors by state:
  - idle: `bg-white text-slate-900` (white button, dark icon)
  - listening: `bg-rose-500 text-white animate-pulse` (red, pulsing)
  - processing: `bg-amber-500 text-white` (amber, with spinner)
  - speaking: `bg-sky-500 text-white` (blue)
- Icon: `Mic` (idle), `MicOff` (listening), `Loader2 animate-spin` (processing), `Volume2` (speaking)
- Shadow: `shadow-xl`
- Hover: `hover:scale-105 transition-transform`

### Waveform Bars (Below/Above Mic Button)
- 5 bars, `w-1.5 rounded-full`
- Color: `bg-white/80`
- Height animated via `scaleY()` transform
- Bars pulse when listening or speaking

### Language Toggle (Below Mic)
- Two pills: `日本語` / `English`
- Active: `bg-white/90 text-slate-900`
- Inactive: `bg-white/20 text-white/70`
- Size: `px-3 py-1.5 text-sm rounded-full`

### Response Bubble (Above Controls or Top)
- Position: above the mic controls, or top-center of screen
- Background: `bg-black/60 backdrop-blur-md rounded-2xl`
- Text color: `text-white`
- Max width: `max-w-lg mx-auto`
- Line clamp: `line-clamp-4`
- Show transcript (user speech) in smaller text above response
- Fade in/out with transition

### Clarification Buttons
- Appear below response bubble when clarification is needed
- Use existing `ClarificationButtons` component
- Style may need adaptation for overlay context (white/transparent backgrounds)

### Slide Overlay (z-40, conditional)
- Background: `bg-black/50 backdrop-blur-sm`
- MarpViewer centered: `mx-auto max-w-5xl`
- Close button: top-right of overlay, `absolute top-4 right-4`
- Aspect ratio maintained for slides

### Text Input (Expandable, Optional)
- Hidden by default (voice-first UX)
- Toggle button below mic: small text link or icon
- When expanded: `bg-white/10 backdrop-blur-md rounded-2xl border border-white/20`
- Textarea + send button

---

## MUST NOT (ABSOLUTE PROHIBITIONS)

1. DO NOT use `max-w-7xl` or any fixed container width for the main layout
2. DO NOT use `bg-slate-100` or `bg-slate-*` as page background colors
3. DO NOT create a grid/dashboard layout with side-by-side panels
4. DO NOT show slides permanently (only on-demand via showSlideMode state)
5. DO NOT put the VRM character inside a card, rounded container, or constrained box
6. DO NOT separate the response text into a separate column/panel
7. DO NOT use `rounded-[28px] border border-slate-200 bg-white/90` card styling for the main sections
8. DO NOT import or use VoiceConversationShell in page.tsx
9. DO NOT add `console.log` or `console.warn` statements
10. DO NOT modify CharacterAvatar.tsx beyond the 3 specific fixes listed above

---

## VERIFICATION CHECKLIST

After implementation, verify ALL of these:

### Build
```bash
cd frontend
pnpm lint       # must pass with zero errors
pnpm typecheck  # must pass with zero errors
pnpm build      # must succeed
```

### Visual (Browser DevTools)
- [ ] VRM character renders fullscreen (fills entire viewport)
- [ ] No white screen / blank canvas
- [ ] Character is centered and properly framed (upper body visible)
- [ ] Mic button is at bottom center, floating over character
- [ ] Response text appears as overlay bubble, NOT in separate panel
- [ ] No dashboard/grid layout visible
- [ ] Slides are NOT visible by default
- [ ] Clicking presentation button opens slide overlay
- [ ] Closing slide overlay returns to fullscreen character

### Console (DevTools Console)
- [ ] No `face-api.js` SRI error
- [ ] No `"surprised" expression not found` warning
- [ ] No application-level errors (VRM 0.0 library warnings are acceptable/known)

### Functionality
- [ ] Mic button starts/stops voice recording
- [ ] Voice response plays with lip-sync
- [ ] Character expressions change with session state (idle/listening/processing/speaking)
- [ ] Language toggle (ja/en) works
- [ ] Text input (when expanded) can send messages
- [ ] Clarification buttons appear when backend sends clarification metadata
- [ ] Slide overlay opens/closes correctly
- [ ] MarpViewer works within slide overlay

---

## EXISTING COMPONENTS TO REUSE (DO NOT RECREATE)

| Component | Path | Purpose |
|-----------|------|---------|
| `CharacterAvatar` | `frontend/src/app/components/CharacterAvatar.tsx` | VRM 3D rendering (1446 lines, complex) |
| `VoiceInterface` | `frontend/src/app/components/VoiceInterface.tsx` | Voice session management (render-prop) |
| `ClarificationButtons` | `frontend/src/app/components/ClarificationButtons.tsx` | Tap-to-select clarification options |
| `MarpViewer` | `frontend/src/app/components/MarpViewer.tsx` | Marp slide presentation |
| `BackgroundSelector` | `frontend/src/app/components/BackgroundSelector.tsx` | Background options (used by CharacterAvatar) |
| `cn()` | `frontend/src/lib/cn.ts` | Simple className joiner |
| `ClarificationUtils` | `frontend/src/lib/clarification-utils.ts` | Extract clarification options from response |

---

## IMPORTS REFERENCE FOR NEW page.tsx

```tsx
'use client';

import { cn } from '@/lib/cn';
import { ClarificationUtils } from '@/lib/clarification-utils';
import {
  ChevronDown,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  Presentation,
  Play,
  SendHorizontal,
  Volume2,
  X,
  XCircle,
} from 'lucide-react';
import { useCallback, useState } from 'react';
import { BackgroundOption } from './components/BackgroundSelector';
import CharacterAvatar from './components/CharacterAvatar';
import ClarificationButtons from './components/ClarificationButtons';
import MarpViewer from './components/MarpViewer';
import VoiceInterface, { type VoiceSessionState } from './components/VoiceInterface';
```

---

## TAILWIND CSS VERSION WARNING

This project uses **Tailwind CSS v3.4.17**. DO NOT use Tailwind v4 syntax. Specifically:
- Use `className="..."` (not CSS-in-JS)
- PostCSS config uses `tailwindcss: {}` (NOT `@tailwindcss/postcss`)
- `h-[100svh]` is valid in Tailwind v3

---

## SUMMARY

The core task is to restore the VTuber/AITuber-style fullscreen UI where:
1. VRM character = fullscreen background canvas (`absolute inset-0 -z-10`)
2. All UI = floating overlays on top of the character
3. Voice button = large circle at bottom center
4. Response = semi-transparent bubble overlay
5. Slides = conditional modal overlay (NOT always visible)
6. Console errors = zero

This follows the exact same pattern used by pixiv/ChatVRM, tegnike/aituber-kit, and pixiv/local-chat-vrm.

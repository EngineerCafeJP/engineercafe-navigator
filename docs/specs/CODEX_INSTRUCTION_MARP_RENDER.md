# Codex Implementation Instruction: Marp render_with_narration

## Overview

`/api/marp` endpoint currently returns 500 because it proxies to backend `/api/slides` with `action: "render_with_narration"`, but the backend only supports `narrate/next/previous/goto/question` actions. This is a fundamental architecture mismatch.

**Goal**: Implement a 3-layer architecture where the backend serves raw markdown + narration data, and the frontend renders HTML using `@marp-team/marp-core`.

---

## Architecture

```
[MarpViewer.tsx]
    | POST /api/marp { action: "render_with_narration", slideFile, language, ... }
    v
[Frontend /api/marp/route.ts]
    | 1. Call backend: POST /api/slides/content { language }
    | 2. Receive: { markdown, narrationData, metadata }
    | 3. Use MarpProcessor to render markdown -> HTML
    | 4. Return: { success, html, slideData: { slides }, narrationData }
    v
[Backend /api/slides/content]
    | 1. Read markdown file from disk
    | 2. Read narration JSON from disk
    | 3. Return raw data (NO HTML rendering)
```

---

## Backend Changes

### New Endpoint: `POST /api/slides/content`

**File**: `backend/main.py`

Add a new endpoint that returns raw slide content (markdown + narration). Do NOT modify the existing `/api/slides` endpoint.

```python
class SlideContentRequest(BaseModel):
    language: str = "ja"

class SlideContentResponse(BaseModel):
    success: bool
    markdown: Optional[str] = None
    narrationData: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@app.post("/api/slides/content", response_model=SlideContentResponse)
async def slides_content_api(body: SlideContentRequest):
    """Return raw slide markdown and narration data for frontend rendering."""
    try:
        language = body.language or "ja"

        # Read markdown file
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        md_path = os.path.join(backend_dir, "slides", language, "engineer-cafe.md")

        if not os.path.exists(md_path):
            # Fallback to root slides dir
            md_path = os.path.join(backend_dir, "slides", "engineer-cafe.md")

        if not os.path.exists(md_path):
            return SlideContentResponse(success=False, error="Slide file not found")

        with open(md_path, "r", encoding="utf-8") as f:
            markdown = f.read()

        # Read narration JSON
        narration_path = os.path.join(
            backend_dir, "slides", "narration", f"engineer-cafe-{language}.json"
        )
        narration_data = None
        if os.path.exists(narration_path):
            with open(narration_path, "r", encoding="utf-8") as f:
                narration_data = json.load(f)

        return SlideContentResponse(
            success=True,
            markdown=markdown,
            narrationData=narration_data,
            metadata={
                "language": language,
                "title": narration_data.get("metadata", {}).get("title", "Engineer Cafe") if narration_data else "Engineer Cafe",
            },
        )
    except Exception as e:
        logger.exception("slides_content error: %s", e)
        return SlideContentResponse(success=False, error="Internal server error")
```

### File Locations (Backend)
- Markdown (JA): `backend/slides/ja/engineer-cafe.md`
- Markdown (EN): `backend/slides/en/engineer-cafe.md`
- Narration (JA): `backend/slides/narration/engineer-cafe-ja.json`
- Narration (EN): `backend/slides/narration/engineer-cafe-en.json`

### Narration JSON Format
```json
{
  "metadata": { "title": "...", "language": "ja", "speaker": "ja-JP-Neural2-B", "version": "2.0" },
  "slides": [
    {
      "slideNumber": 1,
      "narration": {
        "auto": "...",
        "onEnter": "...",
        "onDemand": { "key": "text" }
      },
      "transitions": { "next": "...", "previous": null }
    }
  ]
}
```

---

## Frontend Changes

### 1. Rewrite `/api/marp/route.ts`

**File**: `frontend/src/app/api/marp/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { getBackendApiUrl } from '@/lib/api/backend-url';
import { MarpProcessor } from '@/lib/marp-processor';

const marpProcessor = new MarpProcessor();

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const language = body.language || 'ja';

    // 1. Fetch raw content from backend
    const backendUrl = `${getBackendApiUrl()}/api/slides/content`;
    const backendResponse = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language }),
    });

    if (!backendResponse.ok) {
      throw new Error(`Backend error: ${backendResponse.statusText}`);
    }

    const backendData = await backendResponse.json();
    if (!backendData.success || !backendData.markdown) {
      throw new Error(backendData.error || 'No markdown content returned');
    }

    // 2. Render markdown to HTML using MarpProcessor
    const processed = marpProcessor.processMarkdown(backendData.markdown);

    // 3. Build full HTML document
    const fullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${backendData.metadata?.title || 'Presentation'}</title>
  <style>${processed.css}</style>
</head>
<body>
  ${processed.html}
</body>
</html>`;

    // 4. Return response matching MarpViewer.tsx expectations
    return NextResponse.json({
      success: true,
      html: fullHtml,
      slideData: {
        slides: processed.slides,
      },
      narrationData: backendData.narrationData,
      slideCount: processed.slides.length,
      metadata: backendData.metadata,
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: 'Failed to render slides',
        ...(process.env.NODE_ENV === 'development' && {
          details: error instanceof Error ? error.message : 'Unknown error',
        }),
      },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({ status: 'ok', backend: 'connected' });
}
```

### 2. MarpProcessor Already Exists

**File**: `frontend/src/lib/marp-processor.ts` (508 lines, already implemented)

Key method used: `processMarkdown(markdown: string): ProcessedMarp`

Returns:
```typescript
interface ProcessedMarp {
  html: string;       // Rendered HTML from Marp
  css: string;        // Generated CSS
  slides: MarpSlide[];  // Parsed slide data
  metadata: MarpMetadata;
}

interface MarpSlide {
  slideNumber: number;
  title?: string;
  content: string;
  notes?: string;
  backgroundImage?: string;
  directives?: Record<string, any>;
}
```

### 3. MarpViewer.tsx Expects This Response Format

**File**: `frontend/src/app/components/MarpViewer.tsx` (lines 374-460)

Request sent:
```json
{
  "action": "render_with_narration",
  "slideFile": "slides/ja/engineer-cafe.md",
  "theme": "engineer-cafe",
  "outputFormat": "both",
  "language": "ja",
  "requestId": "...",
  "options": { "html": true, "markdown": { "breaks": true } }
}
```

Response expected:
```json
{
  "success": true,
  "html": "<html>...</html>",
  "slideData": { "slides": [...] },
  "narrationData": { "metadata": {...}, "slides": [...] },
  "slideCount": 10
}
```

**DO NOT modify MarpViewer.tsx.** The `/api/marp/route.ts` must return a response compatible with this format.

---

## Testing Requirements

### Backend Tests

**File**: `backend/tests/test_main_endpoints.py`

```python
@pytest.mark.asyncio
async def test_slides_content_ja():
    """Test slide content endpoint returns markdown and narration for Japanese."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/slides/content", json={"language": "ja"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "markdown" in data
        assert "marp: true" in data["markdown"]
        assert data["narrationData"] is not None
        assert len(data["narrationData"]["slides"]) > 0

@pytest.mark.asyncio
async def test_slides_content_en():
    """Test slide content endpoint returns markdown and narration for English."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/slides/content", json={"language": "en"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["markdown"] is not None

@pytest.mark.asyncio
async def test_slides_content_invalid_language():
    """Test slide content endpoint with unsupported language falls back gracefully."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/slides/content", json={"language": "zh"})
        assert response.status_code == 200
        data = response.json()
        # Should either succeed with fallback or return error gracefully
        assert "success" in data
```

### Frontend E2E Test (Manual Verification Required)

After deployment, verify from a browser:
1. Open the app URL
2. Click the slide/presentation feature
3. Confirm slides render as HTML (not blank/error)
4. Confirm narration data loads (check slide navigation works)
5. Check browser DevTools Network tab: `/api/marp` returns 200 with `html` field

**curl verification from frontend perspective is NOT sufficient. Open the browser.**

---

## CI/CD Notes

- Backend: `ruff check .` and `black --check .` must pass
- Backend: `pytest` must pass (including new tests)
- Frontend: `pnpm lint`, `pnpm typecheck`, `pnpm build` must pass
- Black line length: default 88 (not 100)

---

## Existing Endpoint (DO NOT MODIFY)

`POST /api/slides` remains unchanged. It handles:
- `narrate` - Get narration for current slide
- `next` / `previous` - Navigate slides
- `goto` - Jump to specific slide
- `question` - Ask about slide content

The new `/api/slides/content` is separate and independent.

---

## Branch & PR

- Branch from: `develop`
- Branch name: `feat/marp-render-with-narration`
- PR target: `develop`
- Commit format: `feat(backend): add /api/slides/content endpoint` and `feat(frontend): rewrite /api/marp to use MarpProcessor`

---

## Summary Checklist

- [ ] Add `POST /api/slides/content` to `backend/main.py`
- [ ] Add backend tests in `backend/tests/test_main_endpoints.py`
- [ ] Rewrite `frontend/src/app/api/marp/route.ts` to fetch from backend + render with MarpProcessor
- [ ] Verify `@marp-team/marp-core` import works in Next.js API route (server-side)
- [ ] Run `ruff check . && black --check . && pytest` (backend)
- [ ] Run `pnpm lint && pnpm typecheck && pnpm build` (frontend)
- [ ] DO NOT modify `MarpViewer.tsx` or existing `/api/slides` endpoint
- [ ] Browser test: open app, verify slides display correctly

# Engineer Cafe Navigator

> AI Voice Agent System for Fukuoka City Engineer Cafe (Monorepo)

**English** | **[Japanese](README.md)**

[![Next.js](https://img.shields.io/badge/Next.js-15.3.2-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8.3-blue)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.0-blue)](https://langchain-ai.github.io/langgraph/)
[![LangSmith](https://img.shields.io/badge/LangSmith-Evaluation-orange)](https://smith.langchain.com/)
[![React](https://img.shields.io/badge/React-19.1.0-61dafb)](https://reactjs.org/)

## Project Overview

Engineer Cafe Navigator is a **multilingual voice AI agent system** that automates customer service at Fukuoka City Engineer Cafe.

This project uses a **monorepo structure** with two main components:

- **Frontend (Next.js)**: TypeScript/React-based frontend application
- **Backend (Python)**: AI agent backend powered by LangGraph

## Project Structure

```
engineer-cafe-navigator2025/
├── frontend/              # Next.js frontend
│   ├── src/              # Source code
│   ├── public/           # Static files
│   ├── package.json      # Node.js dependencies
│   └── ...
├── backend/              # Python LangGraph backend
│   ├── main.py           # FastAPI application
│   ├── workflows/        # LangGraph workflows
│   ├── agents/           # Agent implementations
│   ├── requirements.txt  # Python dependencies
│   └── ...
├── package.json          # Root-level workspace config
└── README.md
```

## Quick Start

### Prerequisites

**Recommended: Docker**
- Docker Desktop
- Docker Compose

**Or local environment:**
- mise (version manager)
- Node.js >= 18.0.0
- pnpm >= 8.0.0
- Python >= 3.11.0

### Docker Setup (Recommended)

1. **Clone the repository**

```bash
git clone https://github.com/EngineerCafeJP/engineercafe-navigator.git
cd engineercafe-navigator
```

2. **Configure environment variables**

**Frontend (.env.local)**
```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
# Other environment variables...
```

**Backend (.env)**
```env
# backend/.env
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

3. **Initial setup and launch**

```bash
# Unified commands via Makefile
make setup  # Initial setup (runs Docker build)
make dev    # Start dev servers (http://localhost:3000, http://localhost:8000)
```

**Other commands:**
```bash
make help              # List available commands
make dev:frontend      # Start frontend only
make dev:backend       # Start backend only
make lint              # Run linters
make clean             # Cleanup
```

### Local Setup (using mise)

1. **Install mise**

```bash
# macOS (Homebrew)
brew install mise

# Or from official site
curl https://mise.run | sh
```

2. **Install project tools**

```bash
mise install  # Auto-installs Node.js, Python, pnpm
```

3. **Install dependencies and start**

```bash
make install  # Install dependencies
make dev      # Start dev servers
```

## Component Details

### Frontend (Next.js)

Next.js-based frontend application. Handles UI and user interactions; AI logic is delegated to the backend (LangGraph).

**Key features:**
- Voice AI agent interface
- VRM character display (Three.js)
- Real-time conversation
- Slide presentations (Marp)

**Details:** [frontend/README.md](frontend/README.md)

### Backend (Python LangGraph)

AI agent backend using Python LangGraph. Provides RESTful API via FastAPI.

**Implemented agents (9+):**
| Agent | Responsibility |
|-------|---------------|
| BusinessInfoAgent | Business hours, pricing, access |
| FacilityAgent | Equipment, Wi-Fi, basement facilities |
| EventAgent | Events, calendar |
| SlideAgent | Slide display, narration |
| GeneralKnowledgeAgent | Web search (out-of-scope questions) |
| MemoryAgent | Conversation history, context |
| ClarificationAgent | Ambiguity resolution |
| VoiceAgent | Voice processing (STT/TTS) |
| CharacterControlAgent | VRM control |

**Key features:**
- LangGraph workflow-based agent execution
- LangSmith evaluation and tracing
- Conversation memory management (3-min TTL)
- Enhanced RAG integration

**Details:** [backend/README.md](backend/README.md)

## Latest Updates

### In Progress: Frontend to LangGraph Migration (2026-01)

Migrating frontend client-side processing to LangGraph backend:
- **[#37](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/37)** QueryClassifier to RouterAgent
- **[#38](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/38)** EmotionTagger to unified agents
- **[#39](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/39)** Conversation memory to LangGraph State
- **[#40](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/40)** Frontend thinning
- **[#42](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/42)** Next.js to Vite migration evaluation

### LangGraph Integration Complete (2026-01-13)

- Monorepo structure migration -- Frontend (Next.js) and Backend (Python LangGraph) separated
- 9 agents implemented -- 62 unit tests passing
- FastAPI backend -- RESTful API integration complete
- LangSmith integration -- Agent evaluation and tracing system
- Test infrastructure -- pytest + AsyncMock comprehensive test suite
- Dev environment -- Docker + mise + Makefile unified commands
- Web search integration -- Google Gemini API with Search Grounding

## Development

### Frontend

```bash
cd frontend
pnpm dev
```

### Backend

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Tests

```bash
# Frontend tests
pnpm test:frontend

# Backend tests
pnpm test:backend
```

## Build

```bash
# Frontend build
pnpm build:frontend

# Production build
cd frontend && pnpm build
```

## Tech Stack

### Frontend
- **Framework**: Next.js 15.3.2
- **Language**: TypeScript 5.8.3
- **UI**: React 19.1.0
- **3D**: Three.js + @pixiv/three-vrm
- **Styling**: Tailwind CSS v3.4.17

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **AI Framework**: LangGraph 0.2.0
- **LLM**: LangChain (OpenRouter, Google Gemini)
- **Evaluation**: LangSmith
- **Database**: Supabase (PostgreSQL + pgvector)

## Documentation

### Comprehensive Docs
- **[docs/README.md](docs/README.md)** - Full documentation index and recommended reading order

### Quick Start
- **[docs/development/AGENT-QUICKSTART.md](docs/development/AGENT-QUICKSTART.md)** - Agent development quick start (10 min)
- **[docs/development/LOCAL-DEVELOPMENT-SETUP.md](docs/development/LOCAL-DEVELOPMENT-SETUP.md)** - Local development setup
- **[docs/development/ENVIRONMENT-VARIABLES.md](docs/development/ENVIRONMENT-VARIABLES.md)** - Environment variables guide

### Key Docs
- **[docs/development/DEVELOPER-GUIDE.md](docs/development/DEVELOPER-GUIDE.md)** - Developer guide
- **[docs/api/API.md](docs/api/API.md)** - API documentation
- **[docs/architecture/SYSTEM-ARCHITECTURE.md](docs/architecture/SYSTEM-ARCHITECTURE.md)** - System architecture
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Deployment guide
- **[docs/development/TROUBLESHOOTING.md](docs/development/TROUBLESHOOTING.md)** - Troubleshooting

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](docs/development/CONTRIBUTING.md) for details.

## License

ISC License

## Acknowledgements

- [LangGraph](https://github.com/langchain-ai/langgraph) - AI agent workflows
- [LangSmith](https://smith.langchain.com/) - Agent evaluation and tracing
- [Next.js](https://nextjs.org/) - React framework
- [FastAPI](https://fastapi.tiangolo.com/) - Python web framework

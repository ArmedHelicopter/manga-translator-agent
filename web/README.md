# Manga Translate Agent Web UI

A modern web interface for the Manga Translate Agent with bilingual support (English/中文).

## Features

- **Project Management**: Create and manage translation projects
- **Real-time Translation Progress**: Monitor translation status via SSE
- **Character Profiles**: Configure character voice patterns and catchphrases
- **Terminology Management**: Build a terminology database for consistent translations
- **Provider Configuration**: Configure multiple AI providers (OpenAI, Anthropic, Gemini, etc.)
- **Batch Processing**: Process multiple inputs in parallel
- **Wiki Export**: Export project data to wiki format
- **Onboarding Tutorial**: Step-by-step guide for first-time users
- **Bilingual Interface**: Full support for English and Chinese

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React)                          │
│  React 18 + Vite + Tailwind CSS + i18next                    │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────▼──────────────────────────────────────┐
│                    Backend (FastAPI)                          │
│  FastAPI + uvicorn + SSE for real-time progress              │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Manga Translate Agent                      │
│  Core translation pipeline, memory, and cultural services    │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Use the existing backend

The web UI is already integrated into `mga/web/app.py`. Start it with:

```bash
python -m uvicorn mga.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000 in your browser.

### Option 2: Use the new React frontend

```bash
cd web
npm install
npm run dev
```

The frontend will start at http://localhost:3000 and proxy API requests to the backend.

## API Endpoints

### Projects
- `GET /api/projects` - List all projects
- `POST /api/projects` - Create a new project
- `GET /api/projects/{id}` - Get project details
- `DELETE /api/projects/{id}` - Delete a project

### Characters
- `GET /api/projects/{id}/characters` - List characters
- `GET /api/projects/{id}/characters/{char_id}` - Get character details
- `PUT /api/projects/{id}/characters/{char_id}` - Save character profile

### Terms
- `GET /api/projects/{id}/terms` - List terminology
- `POST /api/projects/{id}/terms/{term_id}` - Save term

### Providers
- `GET /api/projects/{id}/provider-config` - Get provider configuration
- `POST /api/projects/{id}/provider-config` - Save provider configuration

### Translation
- `POST /api/translate/start` - Start translation
- `POST /api/translate/stop` - Stop translation
- `GET /api/translate/status` - Get translation status
- `GET /api/translate/progress/stream` - SSE progress stream

### Batch
- `GET /api/batch/jobs` - List batch jobs
- `POST /api/batch/jobs` - Create batch job
- `POST /api/batch/jobs/{id}/start` - Start job
- `POST /api/batch/jobs/{id}/pause` - Pause job
- `DELETE /api/batch/jobs/{id}` - Delete job

## Configuration

### Providers

The application supports multiple AI providers with a cascade fallback system:

| Provider | Type | Notes |
|----------|------|-------|
| OpenAI | Primary | GPT-4o, GPT-4o-mini |
| Anthropic | Primary | Claude 3.5 Sonnet, Claude 3 Haiku |
| Gemini | Primary | Gemini 2.5 Pro, Gemini 2.5 Flash |
| DeepSeek | Fallback | Cost-effective |
| Ollama | Local | No API key required |
| LM Studio | Local | No API key required |
| vLLM | Local | OpenAI-compatible |
| OpenRouter | Gateway | Multiple providers |
| llama.cpp | Local | Text-only |

### Stages

Each translation stage can have three provider tiers:
- **Primary**: Used first
- **Fallback**: Used if primary fails
- **Local**: Used if other providers are unavailable

## Development

### Frontend

```bash
cd web
npm install
npm run dev      # Development server
npm run build    # Production build
npm run lint     # Lint code
```

### Backend

The backend is integrated into the main application. To run it:

```bash
python -m uvicorn mga.web.app:create_app --factory --reload
```

## Tech Stack

### Frontend
- React 18
- Vite
- Tailwind CSS
- i18next (internationalization)
- Zustand (state management)
- React Router

### Backend
- FastAPI
- uvicorn
- SSE (Server-Sent Events)
- TOML (configuration)

## License

This project is part of the Manga Translate Agent and is licensed under the GPL-3.0 license.

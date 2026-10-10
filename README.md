# Document Intelligence Platform

This repository is the Day 1 foundation for an AI-powered document intelligence platform. It establishes a clean project layout, a versioned FastAPI backend, a React + Vite frontend, architecture documentation, and a working health check that proves the app can connect locally.

## Implementation status

Completed for Day 1:

- architecture documentation under `docs/`
- minimal FastAPI backend with `GET /api/v1/health`
- Vite + React + TypeScript frontend with backend status polling
- API contract documentation
- backend and frontend automated tests
- local environment configuration examples
- Git-ready project structure

Deferred to future phases:

- document upload and parsing
- legal clause extraction and scoring
- document summarization
- Q&A over document evidence with citations
- retrieval, reranking, embeddings, and vector storage
- LLM provider integration and model routing
- document-specific authorization and access control
- Supabase/PostgreSQL integration
- production deployment and observability

## Architecture overview

The system intentionally separates the browser UI from the trusted backend service boundary.

- Frontend: React + Vite + TypeScript
- Backend: Python + FastAPI
- API style: versioned `/api/v1`
- Local development: frontend calls `http://127.0.0.1:8000` by default
- Planned future components: ingestion pipeline, retrieval pipeline, vector database, and LLM access

See the architecture and decision documents in `docs/architecture.md` and `docs/decisions.md`.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- Git configured locally if you want to create a commit checkpoint

## Backend setup

1. Create and activate the virtual environment from the repository root:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

2. Install backend dependencies:

```bash
cd backend
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Start the API:

```bash
cd backend
source ../.venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app exposes:

- `GET /api/v1/health`
- Swagger UI at `http://127.0.0.1:8000/docs`

## Frontend setup

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Copy the example environment file and adjust as needed:

```bash
cp .env.example .env
```

3. Start the Vite dev server:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Default frontend config uses:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Test commands

Backend tests:

```bash
cd backend
source ../.venv/Scripts/activate
PYTHONPATH=. pytest app/tests -q
```

Frontend tests:

```bash
cd frontend
npm test -- --run
```

## Environment configuration

The backend and frontend each include `.env.example` files. Real `.env` files are intentionally ignored by Git and must not be committed.

## API documentation

- API contract: `docs/api-contract.md`
- Architecture: `docs/architecture.md`
- Decisions: `docs/decisions.md`
- Health endpoint contract: `GET /api/v1/health`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Future phases

The current project intentionally does not include provider API clients, database drivers, vector integrations, embeddings, document parsers, LLM orchestration, or authentication. These remain intentionally deferred to later milestones.

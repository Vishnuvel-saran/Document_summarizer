# Document Intelligence Platform

This repository is the foundation for an AI-powered document intelligence platform. Day 1 established the project structure, frontend shell, FastAPI API health endpoint, and a local health-check integration. Day 2 adds the initial database layer, SQL migration, and runtime configuration support required for a secure Supabase-backed foundation.

## Current implementation status

Completed for Day 1 and Day 2:

- React + Vite frontend with a backend status indicator
- FastAPI API with `GET /api/v1/health`
- `GET /api/v1/db-health` for database reachability checks
- SQLAlchemy + Psycopg configuration module
- versioned SQL migration for the initial schema
- Supabase-oriented environment configuration examples
- JWT verification helper boundary for future authenticated backend routes
- architecture, database, and API documentation
- backend and frontend tests

Deferred to future phases:

- document upload and parsing
- chunk generation and embeddings
- retrieval and reranking
- pgvector or semantic search
- LLM orchestrator and OpenRouter routing
- summarization and legal extraction workflows
- full auth UI and session flows
- production deployment and monitoring

## Architecture overview

The system separates the browser UI from the trusted backend service boundary.

- Frontend: React + Vite + TypeScript
- Backend: Python + FastAPI
- API style: versioned `/api/v1`
- Persistence: Supabase PostgreSQL with SQLAlchemy + Psycopg
- Auth boundary: Supabase Auth + backend JWT verification for future protected routes
- Planned future components: ingestion pipeline, retrieval pipeline, vector database, and LLM access

See the architecture, API, and database documents under `docs/`.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- Git configured locally if you want to create a checkpoint
- A Supabase project and PostgreSQL connection details if you want to test the real DB path

## Backend setup

1. Create and activate the virtual environment:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

2. Install dependencies:

```bash
cd backend
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Configure environment variables:

```bash
cp .env.example .env
```

Update the values in `.env` with your Supabase and database settings. Keep real credentials out of Git.

4. Run the API:

```bash
cd backend
source ../.venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app exposes:

- `GET /api/v1/health`
- `GET /api/v1/db-health`
- Swagger UI at `http://127.0.0.1:8000/docs`

## Supabase and database setup

1. Create a Supabase project if one does not already exist.
2. In the Supabase dashboard, open the SQL editor and run the migration at `backend/migrations/001_initial_schema.sql`.
3. Ensure the database role permissions match the intended execution model.
4. Set the environment values in `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_JWT_SECRET=<jwt-secret>
```

Note: the service-role key must never be exposed to the browser. The frontend should only use non-sensitive client-facing configuration.

## Frontend setup

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Copy the example environment file:

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

## Security assumptions and current status

- Supabase Auth owns user credential management.
- The backend must verify Supabase-issued JWTs before trusting a user identity.
- Database ownership and RLS policies are designed to prevent cross-user access when requests run under a user-scoped role.
- A privileged database role can bypass RLS; therefore the backend must still enforce ownership-aware service logic when using privileged credentials.
- JWT verification is implemented as a reusable helper boundary, but the full Supabase-authenticated request flow remains a future integration step unless the project provides the required keys and configuration.

## API documentation

- API contract: `docs/api-contract.md`
- Architecture: `docs/architecture.md`
- Database design: `docs/database-design.md`
- Decisions: `docs/decisions.md`
- Health endpoint contract: `GET /api/v1/health`
- Database health endpoint: `GET /api/v1/db-health`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Future phases

The current project intentionally does not include provider API clients, database drivers for document workflows, vector integrations, embedding generation, retrieval, or LLM orchestration. These remain deferred to later milestones.

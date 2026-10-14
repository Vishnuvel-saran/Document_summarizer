# Document Intelligence Platform

This repository is the foundation for an AI-powered document intelligence platform. Day 1 established the app foundation, Day 2 added the Supabase database/auth boundary, Day 3 implemented secure PDF/DOCX ingestion, and Day 4 adds structure-aware chunking, embeddings, and pgvector persistence.

## Current implementation status

Completed for Day 1 through Day 4:

- React + Vite frontend with a backend status indicator
- FastAPI API with `GET /api/v1/health`
- `GET /api/v1/db-health` for database reachability checks
- SQLAlchemy + Psycopg configuration module
- versioned SQL migration for the initial schema
- Supabase-oriented environment configuration examples
- JWT verification helper boundary for authenticated backend routes
- secure `POST /api/v1/documents` upload endpoint for PDF/DOCX files
- parser service that extracts text and preserves heading/table blocks
- storage service boundary for a private Supabase Storage bucket
- document metadata persistence in the `public.documents` table
- structure-aware chunking with page, section, table, and source-block provenance
- LangChain `OpenAIEmbeddings` adapter routed to OpenRouter's `openai/text-embedding-3-small`
- pgvector persistence and authenticated `POST /api/v1/documents/{document_id}/process`
- idempotent reprocessing with transactional chunk replacement
- architecture, database, ingestion, and API documentation
- backend and frontend tests

Deferred to future phases:

- vector similarity retrieval and search APIs
- hybrid search and reranking
- LLM orchestrator and OpenRouter routing
- summarization and legal extraction workflows
- full auth UI and session flows
- production deployment and monitoring

The local environment has no `OPENROUTER_API_KEY`, so real OpenRouter embedding calls remain unverified. Unit tests mock embedding responses; the live Supabase integration path uses deterministic stub vectors.

## Architecture overview

The system separates the browser UI from the trusted backend service boundary.

- Frontend: React + Vite + TypeScript
- Backend: Python + FastAPI
- API style: versioned `/api/v1`
- Persistence: Supabase PostgreSQL with SQLAlchemy + Psycopg and pgvector
- Auth boundary: Supabase Auth + backend JWT verification and owner-scoped processing
- Embeddings: backend-only OpenRouter embeddings through LangChain; retrieval remains deferred

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
- `POST /api/v1/documents` for secure PDF/DOCX upload validation and content extraction
- `POST /api/v1/documents/{document_id}/process` for authenticated chunking, embeddings, and vector persistence
- Swagger UI at `http://127.0.0.1:8000/docs`

## Supabase and database setup

1. Create a Supabase project if one does not already exist.
2. For a new database, run `backend/migrations/001_initial_schema.sql` and then `backend/migrations/002_chunk_embeddings.sql` once each. On a database where Day 2 is already applied, run only migration `002`.
3. Create a private Storage bucket named `documents` if it does not already exist.
4. Ensure the database role permissions match the intended execution model.
5. Set the environment values in `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
# Optional: legacy-only for older HS256 Supabase setups.
SUPABASE_JWT_SECRET=
OPENROUTER_API_KEY=<server-side-openrouter-api-key>
EMBEDDING_PROVIDER=openrouter
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_BATCH_SIZE=32
CHUNK_TARGET_TOKENS=500
CHUNK_OVERLAP_TOKENS=75
CHUNK_MAX_TOKENS=700
CHUNK_TOKENIZER_ENCODING=cl100k_base
```

Note: modern Supabase projects normally use JWKS/RS256 verification and do not require `SUPABASE_JWT_SECRET`. The service-role key must never be exposed to the browser. The frontend should only use non-sensitive client-facing configuration.

Keep `OPENROUTER_API_KEY` in the backend environment only. Processing sends extracted document text to the selected OpenRouter embedding model.

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

Opt-in Supabase integration tests (use the configured Supabase database and private Storage bucket; temporary test rows and objects are cleaned up):

```bash
RUN_SUPABASE_INTEGRATION=1 PYTHONPATH=. pytest app/tests/test_pgvector_integration.py -q
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
- Protected upload and processing requests verify Supabase JWTs and derive ownership from the verified `sub` claim.
- Direct SQL uses a privileged database connection, so repository operations explicitly scope document access by both document ID and authenticated owner ID rather than relying only on RLS.

## API documentation

- API contract: `docs/api-contract.md`
- Architecture: `docs/architecture.md`
- Database design: `docs/database-design.md`
- Day 4 chunking and embeddings: `docs/day4-chunking-embeddings.md`
- Troubleshooting history: `docs/issues-and-discoveries.md`
- Decisions: `docs/decisions.md`
- Health endpoint contract: `GET /api/v1/health`
- Database health endpoint: `GET /api/v1/db-health`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Future phases

Retrieval, hybrid search, reranking, summarization, clause extraction, and chat remain deferred. Scanned-document OCR is not implemented.

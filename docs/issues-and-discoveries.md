# Issues and discoveries

Use this file as the running engineering log for concrete issues, how they were diagnosed, what changed, what was rolled back, and what remains to verify. Never put passwords, access tokens, service-role keys, database URLs, or other secrets here.

## 2026-10-14: Day 3 document upload and Supabase integration

### Core issue

The authenticated PDF upload initially failed at several stages, and its first `201 Created` response did not mean the entire persistence path was durable. The request successfully wrote the original PDF to Supabase Storage, but the `public.documents` metadata row was later confirmed missing.

### Errors and observations

- `404 Not Found` on port `8000`: the process then serving that port had only the health and DB-health routes registered. The current app source included `POST /api/v1/documents`; starting it on port `8001` provided a known-current server. Port `8000` later served the upload route too.
- `401 Invalid or expired JWT`: the Bash token was at first pasted incorrectly, then safe server logs identified additional configuration/validation failures: malformed Supabase URL caused `PyJWKClientConnectionError`; missing crypto support prevented ES256 key parsing; and missing expected audience caused `InvalidAudienceError`.
- `400 The PDF does not contain any extractable text`: the test PDF was scanned, with six pages, zero embedded text on every page, and one image per page. OCR is not part of the current parser.
- `500 Document upload failed`: the Supabase project had no Storage buckets. The database health endpoint independently returned `200`.
- `201 Created`: the API returned a successful upload response and the `sample.pdf` object was confirmed in the `documents` Storage bucket. A read-only query for the returned document ID found no corresponding database row.

### Diagnosis methods

- Checked `GET /api/v1/health` and `/openapi.json` to distinguish a running server from a process that had registered the document route.
- Read Uvicorn logs after adding safe diagnostics that log only JWT exception classes, never bearer values.
- Queried the public JWKS endpoint and confirmed it was reachable and included the ES256 signing key.
- Checked runtime configuration without printing credential values; the configured Supabase URL had been malformed as `s:/http/...`.
- Queried `/api/v1/db-health`, listed Storage bucket names, and used a read-only SQL query to verify whether upload metadata persisted.
- Inspected the PDF's page text and image counts with PyMuPDF.
- Ran focused and full backend pytest suites.

### Changes made

- `backend/.env`: corrected `SUPABASE_URL` to an HTTPS URL. This file is local configuration and must remain untracked; do not copy its secrets into this log.
- `backend/app/core/config.py`: corrected `.env` loading to target `backend/.env` directly instead of relying on import order.
- `backend/requirements.txt`: changed PyJWT to include its `crypto` extra so ES256 keys can be parsed.
- `backend/app/auth.py`: allowed ES256 and RS256 JWKS signing keys, required Supabase's `authenticated` audience, and added safe logging of the JWT validation exception class.
- Supabase project setup: created the private `documents` Storage bucket; the service writes user-scoped paths beneath it.
- `backend/app/db.py`: changed `db_session()` from `engine.connect()` to `engine.begin()` so successful writes commit when the context exits.
- `backend/app/tests/test_auth.py` and `backend/app/tests/test_db_health.py`: added coverage for the accepted JWT algorithms/audience and successful DB transaction commit.

### Verification

- Direct Python JWKS retrieval succeeded and parsed the project's ES256 key.
- Focused database tests: `4 passed`.
- Full backend tests after the transaction fix: `11 passed` (six dependency deprecation warnings).
- Live upload before the transaction fix: Storage object exists; metadata row absent.
- The metadata row from the successful upload was repaired using its known Storage path and returned document ID; a subsequent read confirmed the row exists. A new authenticated upload after the transaction fix was not separately run.

### Changes reverted

- No intentional code changes from this investigation were reverted.
- Existing user changes and unrelated untracked files were left untouched.

### Security note

Bearer tokens and a test user's password were pasted into terminal/chat context during debugging. Rotate the test user's password and revoke existing sessions; use a newly issued access token for further tests. Never store those values in this file.

## 2026-10-14: Day 4 chunking, OpenRouter embeddings, and pgvector

### Core issue

The Day 3 extraction and upload path existed, but chunks were not generated, no embedding provider was selected, and the live `document_chunks` table had no vector/provenance fields. DOCX parsing also emitted all paragraphs before all tables, losing body order.

### Diagnosis and provider selection

- Inspected Git status/history, installed packages, parser contract, upload/storage/auth code, initial migration, and actual Supabase constraints.
- Queried Supabase: the existing `(document_id, chunk_index)` unique constraint and cascading foreign key were present; `vector` was absent. The vector extension was available at version `0.8.2`.
- Repaired and verified the previously missing Day 3 metadata row; the earlier `201` had proven the Storage write, not durable metadata persistence. The DB session transaction behavior was corrected and covered by a regression test.
- Added an interleaved DOCX paragraph/table test; it failed before the parser was changed to traverse body XML order, then passed.
- User selected OpenRouter. Official OpenRouter docs verify `POST https://openrouter.ai/api/v1/embeddings`, batched text inputs, the model ID `openai/text-embedding-3-small`, 8192 context length, and catalog prompt pricing of `$0.02 / 1M` tokens as checked on 2026-10-14. Account credits/entitlement were not inspected.
- OpenRouter's docs/catalog do not state the output dimension or document a `dimensions` request parameter. The implementation expects the upstream OpenAI model's default 1536 dimensions and validates responses; a live OpenRouter response has not verified this assumption.
- The provider uses LangChain `OpenAIEmbeddings` only as an OpenAI-compatible HTTP client, with `base_url=https://openrouter.ai/api/v1`; requests route to OpenRouter, not directly to OpenAI.
- No `OPENROUTER_API_KEY` is configured. Real provider output, account entitlement, and billing behavior were not exercised.

### Changes made

- Added tokenizer-backed structure-aware chunking with configurable 500/75/700 token target/overlap/maximum settings and `cl100k_base` counts.
- Added chunk provenance for ordered source blocks, headings/sections, tables, page ranges, token-count method, and deterministic content hashes.
- Added a LangChain OpenAI-compatible embedding client routed to OpenRouter with 32-text batches, a 30-second timeout, two SDK retries, 8192-token input validation, dimension/finiteness/count checks, and sanitized failures.
- Added migration `backend/migrations/002_chunk_embeddings.sql` for pgvector `vector(1536)`, provenance columns, and processing fingerprint/model/error fields. No ANN index was added. Migration was applied live to Supabase.
- Added owner-scoped chunk repository and transactionally replaceable chunk sets; remote embeddings are generated before opening the replacement transaction.
- Added private Storage download and the authenticated processing endpoint/service. It reuses the Day 3 parser and rejects cross-owner access.
- Added fingerprint-based reprocessing skip and sanitized failure status handling.

### Verification

- Full backend suite after the OpenRouter change: `30 passed, 2 skipped` (the skipped tests require explicit live integration opt-in).
- Opt-in live Supabase integration: `2 passed`; it uploaded a temporary synthetic PDF to the private bucket, downloaded it, parsed/chunked it, persisted deterministic stub vectors/provenance to pgvector, confirmed unchanged reprocessing skips embeddings, and cleaned up the temporary row/object.
- Unit tests mock the LangChain embedding client and validate OpenRouter base URL/model configuration, batching, model/vector checks, and sanitized failures.
- Real OpenRouter embeddings remain unverified because `OPENROUTER_API_KEY` is absent.
- Retrieval/search, OCR, ANN indexing, and frontend processing UI remain deferred.

### Changes reverted

- No Day 4 changes were intentionally reverted. Existing user modifications and unrelated untracked files were preserved.

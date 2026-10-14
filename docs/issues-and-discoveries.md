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
- Outstanding live verification: retry a valid, text-based PDF upload after the `engine.begin()` change, then confirm both the Storage object and `public.documents` row exist. A previous `201` response alone must not be treated as proof that both writes persisted.

### Changes reverted

- No intentional code changes from this investigation were reverted.
- Existing user changes and unrelated untracked files were left untouched.

### Security note

Bearer tokens and a test user's password were pasted into terminal/chat context during debugging. Rotate the test user's password and revoke existing sessions; use a newly issued access token for further tests. Never store those values in this file.

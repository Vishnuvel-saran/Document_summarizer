# Day 4: Chunking and embeddings

## Pipeline

`Day 3 extraction -> structure-aware chunks -> LangChain embedding adapter -> OpenRouter -> pgvector`

`POST /api/v1/documents/{document_id}/process` runs this pipeline synchronously for the authenticated document owner. It uses the verified JWT subject for ownership, downloads the original from the private `documents` Storage bucket, and reuses the Day 3 PDF/DOCX parser. Retrieval APIs and search are not part of Day 4.

## Chunking

`StructureAwareChunker` consumes the Day 3 `DocumentExtractionResult` and preserves body order, source block indices, section headings, table rows, and reliable PDF page references. DOCX page numbers remain null because the parser does not know physical page layout. Multi-page chunks use `page_start`/`page_end` and leave `page_number` null.

Defaults are configurable through environment values:

- `CHUNK_TARGET_TOKENS=500`
- `CHUNK_OVERLAP_TOKENS=75`
- `CHUNK_MAX_TOKENS=700`
- `CHUNK_TOKENIZER_ENCODING=cl100k_base`

Counts are exact for the selected `cl100k_base` tokenizer, not universal semantic token counts. Overlap is applied to oversized text splits, not ordinary adjacent paragraphs. Split table chunks repeat the header and retain rows in source metadata.

## Embedding provider

The backend uses LangChain's OpenAI-compatible `OpenAIEmbeddings` adapter as the client transport, pointed at OpenRouter's embeddings API (it does not call OpenAI directly):

- Endpoint: `https://openrouter.ai/api/v1`
- Environment secret: `OPENROUTER_API_KEY`
- Exact routed model ID: `openai/text-embedding-3-small`
- Expected output dimension: `1536` (the upstream OpenAI model's documented default; not confirmed by a live OpenRouter response yet)
- Per-input model context: `8192` tokens
- Provider batch size: `32` texts per adapter batch
- OpenRouter catalog price checked on 2026-10-14: `$0.02 / 1M` prompt tokens; account-specific credits/limits may apply.

OpenRouter's documented embeddings request uses `model`, `input`, and optional `encoding_format`. Its docs do not list a `dimensions` request parameter, so the adapter does not send one. The expected 1536-dimensional output comes from upstream OpenAI's model documentation and is checked at runtime before persistence; OpenRouter's public model catalog does not publish vector dimensions. `text-embedding-3-small` is an alias without an immutable snapshot; the routed model ID, not an upstream version hash, is recorded.

The adapter validates input size, batch result count, vector dimensions, finite values, and model identity where the SDK exposes it; SDK retries are bounded. Provider failures are sanitized and never trigger a different model fallback. Extracted document text is sent to OpenRouter when processing is called. Keep the API key backend-only.

The local environment had no `OPENROUTER_API_KEY` during implementation. LangChain/API configuration is unit-tested, but a real OpenRouter request, account entitlement, latency, and billable output dimension were not verified. Add a key to `backend/.env` before invoking the processing endpoint.

## Persistence and reprocessing

Migration `backend/migrations/002_chunk_embeddings.sql` enables pgvector and adds `vector(1536)`, model identity, token-count method, content hash, source metadata, source block indices, and page ranges. It was applied to the configured Supabase database and verified there. The existing unique `(document_id, chunk_index)` and cascading document foreign key remain in place. No ANN index is created; exact search/index selection belongs to Day 5.

The service downloads/parses/chunks and generates all vectors before the chunk-replacement transaction. It then replaces the full chunk set and marks the document ready atomically. If processing fails, the previous chunk set remains; the document receives `failed` and a sanitized exception class. A fingerprint over source bytes, chunk configuration, chunk hashes, embedding model, and dimension avoids repeated embedding calls for unchanged ready documents.

Database access uses a privileged direct SQL connection that may bypass RLS. Repository methods still constrain document reads, status writes, chunk counts, and chunk listings by both document ID and the verified owner ID. Replacement verifies ownership before deleting/inserting chunks. Private Storage service credentials remain server-only.

## Setup and verification

1. Set `OPENROUTER_API_KEY` in `backend/.env`; do not put it in frontend variables.
2. Confirm migrations `001_initial_schema.sql` and `002_chunk_embeddings.sql` have been applied, and the private `documents` bucket exists.
3. Upload a text-based PDF/DOCX using Day 3's upload endpoint.
4. Call `POST /api/v1/documents/{document_id}/process` with that user's Supabase bearer token.
5. A `ready` response means chunks/vectors were persisted. Repeat processing to check `skipped: true` for an unchanged document.

Run isolated tests with `PYTHONPATH=. pytest app/tests -q`. Run live Supabase Storage/DB tests with `RUN_SUPABASE_INTEGRATION=1 PYTHONPATH=. pytest app/tests/test_pgvector_integration.py -q`; these use synthetic vectors rather than calling OpenRouter.

## Deferred scope and limitations

BM25/vector retrieval, hybrid search, reranking, OCR, summarization, clause extraction, and chat remain deferred. API credentials are required to generate real embeddings. Changing the model or vector dimension requires reprocessing/re-embedding all affected documents and an explicit schema migration if the dimension changes.

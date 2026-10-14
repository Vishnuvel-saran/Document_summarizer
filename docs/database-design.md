# Database design

This document captures the relational schema through Day 4. The goal is to preserve the secure initial model while adding provenance-rich chunks and vectors, without introducing a retrieval API before Day 5.

## Core entities

### profiles

The `profiles` table stores application-facing profile metadata for authenticated Supabase users. It is intentionally minimal and does not store credentials. Supabase Auth owns the authentication lifecycle.

Required fields:

- `id`: UUID primary key referencing `auth.users(id)`.
- `display_name`: optional display name.
- `created_at`: timezone-aware timestamp.

Ownership rule: each row is owned by the same authenticated user referenced by `id`.

### documents

The `documents` table stores document metadata for uploaded files. It is designed for a future ingestion pipeline but currently contains the core metadata needed for ownership and lifecycle management.

Required fields:

- `id`: UUID primary key.
- `user_id`: required user owner.
- `filename`: original document filename.
- `file_type`: restricted to `pdf` or `docx`.
- `storage_path`: private object-storage reference.
- `status`: restricted to `uploaded`, `processing`, `ready`, or `failed`.
- `created_at` and `updated_at`: timezone-aware timestamps.
- `processing_fingerprint`: optional hash of source bytes, chunking settings, and embedding identity used to skip unchanged reprocessing.
- `embedding_model`: optional model identifier for the current processed chunk set.
- `processing_error`: optional sanitized exception class for a recoverable failed processing attempt.

Indexing: the repository adds an index on `(user_id, created_at DESC)` to support ownership-based listings and recent-document queries.

### document_chunks

This table stores extracted text chunks and embeddings. The Day 4 schema uses the selected upstream model's default 1536-dimensional vector size.

Required fields:

- `id`: UUID primary key.
- `document_id`: foreign key to `documents(id)` with cascade delete.
- `chunk_index`: non-negative integer.
- `content`: extracted text.
- `page_number`: optional page hint.
- `section_title`: optional section name.
- `token_count`: optional non-negative integer.
- `page_start` / `page_end`: optional inclusive source page range; `page_number` is populated only for single-page chunks.
- `block_type`: source kind such as paragraph, table, heading, or mixed.
- `source_block_indices` / `source_metadata`: JSONB provenance from Day 3 extraction, including table rows where applicable.
- `token_counting_method`: tokenizer identifier used for the recorded token count.
- `content_hash`: deterministic SHA-256 hash used as part of processing fingerprints.
- `embedding`: nullable `vector(1536)`.
- `embedding_model` / `embedding_dimension`: exact routed model identifier and output dimension for each vector.
- `created_at`: timezone-aware timestamp.

Uniqueness: `(document_id, chunk_index)` is enforced so chunk ordering remains deterministic and repeatable. Reprocessing replaces a document's full chunk set inside one transaction after parsing and all embeddings succeed.

Provenance note: PDF pages are retained; DOCX physical page numbers remain null because the parser cannot infer page layout. Multi-page chunks use ranges and leave `page_number` null. Split tables repeat the header and retain source rows in JSONB metadata.

Vector strategy: exact vector storage only; no ANN index is created at this initial scale. Day 5 owns search operators and retrieval/index evaluation. Searches must filter by `embedding_model`; vectors from different models are not comparable even if dimensions match.

### conversations

The `conversations` table stores per-document conversation threads created by a user.

Required fields:

- `id`: UUID primary key.
- `user_id`: authenticated owner.
- `document_id`: associated document.
- `title`: defaulted to a sensible conversation title.
- `created_at` and `updated_at`: timezone-aware timestamps.

Ownership invariant: the conversation owner and the associated document owner must match. The SQL schema uses an ownership-based foreign-key design and the conversation policies enforce this at the database level whenever feasible.

### messages

`messages` stores the content of the chat history for a conversation.

Required fields:

- `id`: UUID primary key.
- `conversation_id`: foreign key to `conversations(id)` with cascade delete.
- `role`: restricted to `user` or `assistant`.
- `content`: message content.
- `evidence`: JSONB array defaulting to an empty array.
- `created_at`: timezone-aware timestamp.

Indexing: the repository adds an index on `(conversation_id, created_at DESC)` to support chronological retrieval.

## Relationships

- `auth.users` to `profiles`: one-to-one by user id.
- `auth.users` to `documents`: one-to-many by `user_id`.
- `documents` to `document_chunks`: one-to-many by `document_id`.
- `auth.users` to `conversations`: one-to-many by `user_id`.
- `documents` to `conversations`: one-to-many by `document_id`.
- `conversations` to `messages`: one-to-many by `conversation_id`.

## Constraints and policy assumptions

- All timestamp columns use `TIMESTAMPTZ`.
- Supported document types are constrained to `pdf` and `docx`.
- Status values are constrained to `uploaded`, `processing`, `ready`, and `failed`.
- Message roles are constrained to `user` and `assistant`.
- `chunk_index` and `token_count` cannot be negative.
- RLS is enabled on all private tables and access is restricted by ownership-based policies.

## Database migration handling

The repository stores the schema in versioned migration files:

- `backend/migrations/001_initial_schema.sql` — initial relational schema.
- `backend/migrations/002_chunk_embeddings.sql` — pgvector extension, vector/provenance fields, and processing fingerprints.

Apply migration `002` once after `001` on an existing Day 2 database. It has been applied and verified against the configured Supabase project. Review migrations before applying them to another existing database.

## Supabase-specific execution model

This project assumes the following execution model:

- Supabase Auth is responsible for user authentication.
- FastAPI verifies Supabase-issued JWTs and derives the authenticated user identity.
- PostgreSQL enforces ownership with Row Level Security.
- A privileged database role may bypass RLS in some contexts, so the backend must still enforce ownership checks when using privileged service credentials.

This is a secure design boundary, but it is not a substitute for application-level validation when a privileged database role is in use.

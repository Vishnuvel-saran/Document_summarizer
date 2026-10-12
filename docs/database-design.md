# Database design

This document captures the initial relational schema for the Day 2 database foundation. The goal is to provide a secure, versioned, and extensible foundation for future document memory, retrieval, and Q&A features without building speculative retrieval logic today.

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

Indexing: the repository adds an index on `(user_id, created_at DESC)` to support ownership-based listings and recent-document queries.

### document_chunks

This table stores extracted text chunks for a document. At Day 2 the schema intentionally avoids a fixed vector column; the embedding strategy and dimension count will be selected during the retrieval phase.

Required fields:

- `id`: UUID primary key.
- `document_id`: foreign key to `documents(id)` with cascade delete.
- `chunk_index`: non-negative integer.
- `content`: extracted text.
- `page_number`: optional page hint.
- `section_title`: optional section name.
- `token_count`: optional non-negative integer.
- `created_at`: timezone-aware timestamp.

Uniqueness: `(document_id, chunk_index)` must be unique so chunk ordering remains deterministic and repeatable.

Provenance note: richer chunk provenance may be needed later for multi-page tables, repeated sections, or content spanning multiple source locations.

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

The repository stores the initial schema as a repeatable migration file:

- `backend/migrations/001_initial_schema.sql`

This makes the schema reproducible in a new project and explains how to reapply it when a database is newly provisioned. If a migration has already been applied, the SQL should be reviewed carefully before re-running it on an existing target, especially if there is any production or user data present.

## Supabase-specific execution model

This project assumes the following execution model:

- Supabase Auth is responsible for user authentication.
- FastAPI verifies Supabase-issued JWTs and derives the authenticated user identity.
- PostgreSQL enforces ownership with Row Level Security.
- A privileged database role may bypass RLS in some contexts, so the backend must still enforce ownership checks when using privileged service credentials.

This is a secure design boundary, but it is not a substitute for application-level validation when a privileged database role is in use.

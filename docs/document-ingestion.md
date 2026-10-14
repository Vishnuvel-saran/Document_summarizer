# Document ingestion pipeline

## Overview

The Day 3 ingestion flow is intentionally minimal and secure. It validates the user, checks file size and extension, extracts text from the uploaded PDF or DOCX document, stores the file in a private Supabase Storage bucket, and persists its metadata in the `public.documents` table.

## Components

- `app.services.document_parser` parses uploaded content into structured blocks.
- `app.services.storage_service` uploads files to a private Supabase bucket through the service-role client.
- `app.main.upload_document` coordinates validation, parsing, storage, and database persistence.
- `public.documents` stores the user ID, filename, file type, storage path, and status.

## Security notes

- The upload endpoint is protected by `get_current_user`, which verifies the Supabase JWT before trusting the caller.
- Only `pdf` and `docx` are allowed; other types are rejected early.
- The service-role client is used only for server-side writes to the private storage bucket and never exposed to the browser.
- The upload path remains scoped to the current user to keep access boundaries aligned with the RLS model.

## Storage expectation

The default storage bucket name is `documents`, and the upload path is intentionally shaped as:

```text
<user_id>/<document_id>/<filename>
```

This keeps documents isolated per user and creates a natural path for later retrieval and permission checks.

## Extraction contract

The parser returns a `DocumentExtractionResult` containing:

- `file_type` (`pdf` or `docx`)
- `filename`
- `blocks` with normalized text blocks
- `warnings` for pages or sections that could not be extracted

PDF blocks are page-aware and keep a source page number. DOCX blocks preserve heading and table structure where possible.

## Future extension points

The Day 4 processing endpoint reuses these extraction blocks to create structure-aware chunks, obtain embeddings through OpenRouter, and persist provenance/vector rows. Retrieval, search, and Q&A remain future work.

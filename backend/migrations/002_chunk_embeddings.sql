BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE public.document_chunks
    ADD COLUMN page_start INTEGER,
    ADD COLUMN page_end INTEGER,
    ADD COLUMN block_type TEXT,
    ADD COLUMN source_block_indices JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN token_counting_method TEXT,
    ADD COLUMN content_hash TEXT,
    ADD COLUMN embedding vector(1536),
    ADD COLUMN embedding_model TEXT,
    ADD COLUMN embedding_dimension INTEGER;

UPDATE public.document_chunks
SET page_start = page_number,
    page_end = page_number
WHERE page_number IS NOT NULL;

ALTER TABLE public.document_chunks
    ADD CONSTRAINT document_chunks_page_range_check
        CHECK (
            (page_start IS NULL AND page_end IS NULL)
            OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start <= page_end)
        ),
    ADD CONSTRAINT document_chunks_embedding_dimension_check
        CHECK (embedding_dimension IS NULL OR embedding_dimension = 1536);

ALTER TABLE public.documents
    ADD COLUMN processing_fingerprint TEXT,
    ADD COLUMN embedding_model TEXT,
    ADD COLUMN processing_error TEXT;

COMMIT;

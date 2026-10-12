BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'docx')),
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id_created_at
    ON public.documents (user_id, created_at DESC);

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    page_number INTEGER,
    section_title TEXT,
    token_count INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON public.document_chunks (document_id, chunk_index);

ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Untitled conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT conversations_user_document_match
        CHECK (user_id = auth.uid())
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id_document_id
    ON public.conversations (user_id, document_id);

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at
    ON public.messages (conversation_id, created_at DESC);

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_owner_select"
    ON public.profiles
    FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "profiles_owner_insert"
    ON public.profiles
    FOR INSERT
    WITH CHECK (auth.uid() = id);

CREATE POLICY "profiles_owner_update"
    ON public.profiles
    FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

CREATE POLICY "documents_owner_select"
    ON public.documents
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "documents_owner_insert"
    ON public.documents
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "documents_owner_update"
    ON public.documents
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "documents_owner_delete"
    ON public.documents
    FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "document_chunks_owner_select"
    ON public.document_chunks
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = document_chunks.document_id
              AND d.user_id = auth.uid()
        )
    );

CREATE POLICY "document_chunks_owner_insert"
    ON public.document_chunks
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = document_chunks.document_id
              AND d.user_id = auth.uid()
        )
    );

CREATE POLICY "document_chunks_owner_update"
    ON public.document_chunks
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = document_chunks.document_id
              AND d.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = document_chunks.document_id
              AND d.user_id = auth.uid()
        )
    );

CREATE POLICY "document_chunks_owner_delete"
    ON public.document_chunks
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = document_chunks.document_id
              AND d.user_id = auth.uid()
        )
    );

CREATE POLICY "conversations_owner_select"
    ON public.conversations
    FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "conversations_owner_insert"
    ON public.conversations
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "conversations_owner_update"
    ON public.conversations
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "conversations_owner_delete"
    ON public.conversations
    FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "messages_owner_select"
    ON public.messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.user_id = auth.uid()
        )
    );

CREATE POLICY "messages_owner_insert"
    ON public.messages
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.user_id = auth.uid()
        )
    );

CREATE POLICY "messages_owner_update"
    ON public.messages
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1
            FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.user_id = auth.uid()
        )
    );

CREATE POLICY "messages_owner_delete"
    ON public.messages
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1
            FROM public.conversations c
            WHERE c.id = messages.conversation_id
              AND c.user_id = auth.uid()
        )
    );

COMMIT;

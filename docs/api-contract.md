# API contract

## Initial implemented endpoints

### GET /api/v1/health

Purpose: return the health state of the backend service for local development and environment monitoring.

Successful status code: `200 OK`

Response JSON schema:

```json
{
  "status": "ok",
  "service": "document-intelligence-api"
}
```

Example response:

```json
{
  "status": "ok",
  "service": "document-intelligence-api"
}
```

Expected behavior if the backend is unavailable:

- the frontend should show a backend unavailable state;
- the HTTP request may fail with a network error or connection refused error;
- the client should not crash and should provide a retry mechanism.

### POST /api/v1/documents

Purpose: accept an authenticated PDF or DOCX upload, validate the file size and type, parse text content, and persist the document metadata with a storage path.

Successful status code: `201 Created`

Request type: multipart form-data with a single file field named `file`.

Required auth: Bearer token verified by the Supabase JWT boundary.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H "Authorization: Bearer <jwt>" \
  -F "file=@sample.pdf"
```

Example response:

```json
{
  "id": "8d68f59b-2eb6-4269-836e-024a4d6f4c67",
  "filename": "sample.pdf",
  "file_type": "pdf",
  "status": "uploaded",
  "storage_path": "user-123/8d68f59b-2eb6-4269-836e-024a4d6f4c67/sample.pdf",
  "extraction": {
    "block_count": 2,
    "warnings": []
  }
}
```

Validation rules:

- only `.pdf` and `.docx` files are accepted;
- files exceeding 15 MB are rejected with `413`;
- empty files are rejected with `400`;
- invalid or unreadable content is rejected with `400`;
- the endpoint requires a valid bearer token.

## Planned endpoints

The following endpoints are intentionally planned for later phases and are not implemented here.

### GET /api/v1/documents

Planned. This endpoint will list documents available to the current user or service context.

### GET /api/v1/documents/{document_id}

Planned. This endpoint will fetch a document record and its current metadata.

### POST /api/v1/documents/{document_id}/chat

Planned. This endpoint will accept a question about a document and return a grounded answer, likely with citation metadata.

### POST /api/v1/documents/{document_id}/summary

Planned. This endpoint will generate a summary of a document or selected section.

### GET /api/v1/documents/{document_id}/findings

Planned. This endpoint will expose extracted findings, legal clauses, obligations, deadlines, penalties, exceptions, and renewal language.

Document-specific authorization will be enforced by the backend when these endpoints are implemented. The frontend will not be trusted to enforce document access restrictions.

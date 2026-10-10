# API contract

## Initial implemented endpoint

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

## Planned endpoints

The following endpoints are intentionally planned for later phases and are not implemented on Day 1.

### POST /api/v1/documents

Planned. This endpoint will support document upload and initial metadata handling.

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

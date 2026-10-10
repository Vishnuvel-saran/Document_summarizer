# Architecture

This repository is intentionally a Day 1 foundation for a document intelligence platform. It establishes the application shell, versioned API boundary, and the minimal working connection between a lightweight React frontend and a FastAPI backend. The platform will evolve in later phases to include ingestion, retrieval, orchestration, and secure document-aware AI workflows.

## Frontend responsibilities

The frontend is a React + Vite + TypeScript client responsible for:

- presenting the product landing experience;
- showing the application status and backend health information;
- capturing user intent for later document workflows;
- providing a clean UI boundary for future upload, summary, and Q&A workflows.

The frontend does not own model-provider access, database connectivity, or document-processing logic. It only calls the backend API and presents results.

## Backend API responsibilities

The FastAPI backend owns the publicly exposed API boundary and is responsible for:

- exposing a versioned API under `/api/v1`;
- validating request shapes and response contracts;
- enforcing application-level controls such as origin policy and centralized error handling;
- routing future document workflows through a stable API contract;
- managing access control and provenance-aware logic for document-scoped operations when those features are introduced.

The current backend does only one implemented responsibility: returning the application health status.

## Application-service boundary

The application boundary sits between the UI and the external service ecosystem. The backend is the trusted execution environment for application logic and external system access. This separation keeps provider credentials, policy decisions, and future orchestration behind an internal service boundary.

This is especially important for document intelligence workloads, where validation, authorization, provenance, and output integrity must remain application-controlled rather than delegated to browser-side code.

## Future document ingestion pipeline

A future ingestion pipeline will likely perform the following stages:

1. document upload and initial validation;
2. file-type and policy checks;
3. parsing into a structured representation;
4. document normalization and metadata extraction;
5. structure-aware chunking;
6. embedding generation and storage;
7. indexing and retrieval preparation.

This pipeline is planned and intentionally not implemented on Day 1.

## Future retrieval and generation pipeline

The future retrieval-and-generation flow is expected to be:

Document upload → Validation → Parsing → Structure-aware chunking → Embeddings and storage → Retrieval → Optional reranking → Context assembly → LLM generation → Output validation → Cited response.

The retrieval layer will assemble only a relevant subset of document evidence for a request. The generation layer will synthesize a response grounded in those evidence fragments and return source provenance for downstream citation. Summarization and fine-print extraction must eventually operate systematically over the complete document structure instead of depending only on a top-k chunk approximation.

## Future persistence layer

A future persistence layer will likely include:

- a relational database for document metadata and user/task records;
- vector storage or embeddings storage for semantically searchable evidence;
- provenance metadata linking generated answers back to source document segments.

The database, vector store, and storage interfaces are planned components and are not part of Day 1 implementation.

## Security and validation boundaries

The architecture keeps key controls in the backend, including:

- CORS policies restricted to known local origins;
- centralized error handling that hides internal details from clients;
- future authorization checks for access to specific documents and evidence;
- validation of request and output boundaries before any downstream AI or storage step.

The browser is not trusted to enforce business logic or handle secret material. It can only present UI and call the backend.

## Data flow from document upload to cited answer

The intended future data flow is:

1. the user uploads a document through the frontend;
2. the backend validates file metadata and access constraints;
3. the content is parsed and normalized into a structured representation;
4. the document is chunked with structure awareness;
5. embeddings are generated and stored alongside source metadata;
6. the retrieval stage selects relevant context for the task;
7. optional reranking and context assembly refine the evidence set;
8. the LLM generates a response grounded in the selected context;
9. the backend validates the output and preserves evidence provenance;
10. the frontend shows the final answer with citations and source references.

This architecture is intentionally lightweight and extensible, with the Day 1 implementation only establishing the foundation for later document intelligence workflows.

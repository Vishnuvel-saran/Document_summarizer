# Key architectural decisions

## Why React + Vite is separated from FastAPI

The frontend and backend are intentionally separated so each layer can evolve independently. The browser is optimized for interactive UI experiences, while the backend is the secure trusted boundary for service orchestration, validation, and policy enforcement.

## Why the backend owns model-provider access

Model-provider access, routing, instrumentation, and future secret management must remain in the backend. This keeps provider keys and provider-specific behavior behind the application boundary and away from browser code.

## Why the API is versioned

A versioned API prefix (`/api/v1`) provides a stable contract for the frontend and future services. It allows the application to evolve without breaking clients that depend on known response shapes.

## Why source provenance must be preserved for future citations

Citations depend on traceable evidence. Without preserving provenance links from generated answers back to chunks, sections, or document source references, the platform cannot provide trustworthy cited responses or explainability.

## Why authorization and evidence validation must remain application-controlled

Document access, evidence selection, and output validation are security-sensitive concerns. They cannot be delegated to the browser or to external services without a trusted backend layer that enforces policy and validates responses before they are returned to users.

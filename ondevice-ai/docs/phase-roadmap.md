# Runtime Platform Roadmap

This document outlines the implementation plan for **Phase 1 (Core runtime & infra MVP)** and **Phase 2 (Model platform foundation)**. It breaks larger goals into milestones with sequencing assumptions, ownership notes, and measurable deliverables.

---

## Phase 1 – Core runtime & infrastructure MVP

| Milestone | Scope | Key Outputs | Dependencies |
|-----------|-------|-------------|--------------|
| P1.1 – Cross-platform packaging | Produce single-entry binaries for macOS, Linux, Windows using PyInstaller bundles + OS specific installer scripts (PKG/DMG, .deb/.rpm, MSI). Add CI matrix jobs to build/upload artifacts. | `packaging/` scripts per OS, GitHub Actions release workflow, installer README. | Existing PyInstaller spec (`packaging/OnDeviceAI.spec`), signing credentials TBD. |
| P1.2 – Supervisor health orchestration | Extend supervisor with restart hooks, exponential backoff tuning via config, liveness/readiness probes (Unix socket/HTTP). Surface metrics via `daemon status` and `/healthz`. | Updated `core/supervisor.py`, health probe module, CLI enhancements, pytest coverage. | P1.1 packaging uses supervisor binaries. |
| P1.3 – Sandbox hardening | Add pluggable resource limit adapters (cgroups v2 on Linux, Windows Job Objects, Firejail optional). Provide configuration schema, detection, and graceful degradation on unsupported hosts. | New `core/sandbox_adapters/` package, unit tests, docs for permissions. | Requires OS-specific testing infra. |
| P1.4 – Authenticated endpoints | Introduce bootstrap token + API key auth across HTTP/gRPC/WebSocket. Ship proto updates and auto-generated OpenAPI spec. | Updated `proto/assistant.proto`, generated stubs, middleware enforcing auth, docs. | Dependent on packaging to ship credentials. |
| P1.5 – Diagnostics & telemetry | Expand diagnostics bundle with system metrics, crash dumps, anonymized telemetry opt-in (config flag). Implement background uploader stub. | Extended `core/diagnostics.py`, new telemetry module, CLI toggles, tests. | Leverages supervisor logs.

### Sequencing Notes
1. **P1.1** unblocks multi-platform distribution; run in parallel with P1.2 where feasible.
2. **P1.3** depends on OS-level research—start with feature flags and CI checks in containers/VMs.
3. **P1.4** requires proto changes → regenerate bindings and ensure clients updated simultaneously.
4. **P1.5** builds on diagnostics foundation completed in Phase 0; implement opt-in collection with privacy review.

### Acceptance Criteria
- Packaging job produces installers for all target OSs with smoke-test workflow.
- Supervisor exposes health endpoints, restart hooks logged & test-covered.
- Sandbox adapters enforce CPU/memory/process caps on supported hosts and fail soft elsewhere.
- All API surfaces require auth token unless explicitly disabled in config.
- Diagnostics bundle includes telemetry toggle, crash dumps, environment snapshot, and optional uploader stub.

---

## Phase 2 – Model platform foundation

| Milestone | Scope | Key Outputs | Dependencies |
|-----------|-------|-------------|--------------|
| P2.1 – Local model registry & cache | Store metadata for installed/available models, manage download queue, verify checksums, support import/export. | `core/model_registry.py`, persistent SQLite/JSON store, CLI/daemon APIs to list/install/remove models. | Requires auth (P1.4) for remote downloads. |
| P2.2 – Quantization & tooling pipeline | Provide quantization scripts (ggml/gguf, mlx) with automation pipeline, optional GPU acceleration, reproducible metadata. | `tools/quantize.py` enhancements, workflow docs, CI job for sample quantization. | Depends on registry for target metadata. |
| P2.3 – Runtime adapter interface | Define abstraction allowing ggml, Ollama, vLLM, custom REST runtimes. Support hot load/unload, health & readiness checks, automatic fallback. | `core/model_adapter.py` refactor, adapter base class, adapter registry, tests. | Builds on orchestrator runtime selection. |
| P2.4 – Embeddings & vector store refresh | Integrate streaming token output, configurable embedding backends, improved indexing pipeline with background jobs. | Updated `core/vector_store.py`, streaming gRPC responses, chunking utilities. | Depends on adapters for embedding models. |
| P2.5 – Prompt template management | Provide templating DSL, versioning, compression utilities, and CLI/HTTP APIs for managing prompt packs. | `core/prompt_templates/` module, serialization format, documentation, tests. | Enables richer orchestrator flows.

### Sequencing Notes
1. Registry (P2.1) underpins all later milestones—prioritize metadata schema & CLI/API integration.
2. Quantization pipeline (P2.2) can iterate in parallel once registry provides model descriptors.
3. Adapter architecture (P2.3) is foundational for embeddings and streaming; focus on clear interfaces + lifecycle management.
4. Embeddings/vector store update (P2.4) leverages streaming support in adapters; ensure existing tests adapt to streaming API.
5. Prompt utilities (P2.5) finalize developer ergonomics; align with orchestration roadmap.

### Acceptance Criteria
- Models can be listed/installed/removed with integrity checks and disk quota awareness.
- Quantization pipeline produces reproducible artifacts with metadata traceability.
- Adapters load/unload models at runtime with health reporting and fallback on failure.
- Vector store supports streaming updates and multiple embedding providers without code changes.
- Prompt templates are versioned, compressible, and exposed via CLI/API with documentation.

---

## Cross-cutting concerns

- **Security & Auth:** All new services honor auth tokens, TLS-ready configuration, and secrets management introduced in Phase 0.
- **Observability:** Extend metrics/logging to cover adapters, registry operations, and sandbox limits. Update diagnostics bundle accordingly.
- **Automation:** Expand CI to run OS-specific checks, linting, mypy (if adopted), and integration tests for registry/adapters.
- **Documentation:** Each milestone requires README additions, API reference updates, and migration notes when configs change.

## Next Steps

1. Approve milestone plan and adjust priorities or ownership.
2. Spin up feature branches per milestone with tracking issues.
3. Begin with **P1.1** (packaging) + **P1.2** (supervisor health) in parallel, establishing baseline automation for subsequent work.
4. Schedule design reviews for sandbox adapters (P1.3) and adapter architecture (P2.3) before implementation.

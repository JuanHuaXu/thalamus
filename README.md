# Thalamus

Universal Memory Middleware for OpenClaw and Cognee.

## Features
- **Decoupled Architecture**: Thin OpenClaw plugin + Rich Python middleware.
- **Evolutionary Knowledge Hub**: Automated feedback loop that rewards successful facts and penalizes "brain rot" based on real-world outcomes.
- **Dynamic Scaling Mitigations**: Penalty-based knowledge decay and configurable ingestion queue limits.
- **LLM Provider Orchestration**: Lazy-pull support for missing Ollama models during synthesis.
- **Binary Ingestion Sanitizer**: Proactive detection of base64 "brain rot", stripping images (with metadata extraction), and text extraction from embedded PDFs.
- **Latent Space Abstraction (LSA)**: 3-Stage retrieval (Surgical → Broad → Analogous) to bridge knowledge gaps and prevent hallucinations.
- **Authoritative Web Seeding**: Bulk-ingest documentation, PDFs, and raw code directly into the graph.
- **Consolidation Engine**: Background synthesis to merge conflicting facts and prune obsolete data.
- **Cognee Integration**: Native graph-based memory and context extraction.
- **Performance Tiers (Race Car Mode)**: Hybrid `CHUNKS`/`GRAPH` search with parallelized I/O across agent and documentation datasets.
- **Multi-Tier Persistence**: Sub-10ms in-memory (L1) caching and sub-50ms SQLite-backed (L2) result bypass for recurring queries.
- **Fail-Fast Parallelization**: Hard 25s timeouts for backend search tasks to ensure middleware responsiveness.
- **Robustness Suite**: Comprehensive V1.4 test coverage verifying persistence, search timeouts, and core semantic logic.
- **Tool Reliability Ranking**: SQLite-backed tracking of tool success/failure to guide agent behavior.
- **Webhook Pipeline**: Real-time events (`MEMORIES_PUSHED`, `MEMORIES_SYNCED`) for ecosystem observability.

## Quick Start

1. **Installation & Setup**:
   ```bash
   chmod +x scripts/*.sh
   ./scripts/install.sh
   ```
   *This creates a `.venv`, installs dependencies, and bootstraps `config.json`.*

2. **Service Management**:
   ```bash
   # Start the service
   ./scripts/service.sh start

   # Check status or logs
   ./scripts/service.sh status
   tail -f logs/thalamus.log
   ```
   *Server runs at `http://127.0.0.1:8080`.*

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/context` | `GET` | Fetches formatted context block (cached). |
| `/v1/ingest` | `POST` | Manually ingest message turns into the graph. |
| `/v1/seed` | `POST` | Authoritative ingestion from documentation URLs. |
| `/v1/sync` | `POST` | Sync OpenClaw session logs for an agent. |
| `/v1/consolidate` | `POST` | Trigger background knowledge synthesis pass. |
| `/v1/context/bulk-dispute` | `POST` | Selectively hide nodes matching a search query. |
| `/v1/search` | `POST` | Low-level graph search. |
| `/v1/tools/stats/{id}` | `GET` | Retrieve tool reliability metrics. |

## Documentation
- [Architecture Overview](docs/architecture.md)
- [Configuration Reference](docs/configuration.md)
- [API Contracts](docs/api_contracts.md)
- [Implementation Walkthrough](docs/walkthrough.md)

## License
MIT

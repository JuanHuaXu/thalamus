# Thalamus

Universal Memory Middleware for OpenClaw and Cognee.

## Features
- **Decoupled Architecture**: Thin OpenClaw plugin + Rich Python middleware.
- **Semantic Topic Isolation (V1.8)**: LLM-powered query subject extraction and search result vetting to prevent cross-topic search leakage.
- **Robust Document Ingestion (V1.9)**: Bulletproof crawler with granular timeouts, retry loops, and an **HTTP/1.1 Protocol Lock** to bypass buggy H2 stacks on financial portals.
- **Direct Ingestion Fallback**: Bypasses WAF blocks by allowing users to provide text content directly to the seeding endpoint.
- **Asynchronous Job Tracking (V2.0)**: Persistent Job Registry with unique `job_id` tracking and explicit status polling (`PENDING` -> `RUNNING` -> `COMPLETED`/`FAILED`).
- **Evolutionary Knowledge Hub**: Automated feedback loop that rewards successful facts and penalizes "brain rot" based on real-world outcomes.
- **Dynamic Scaling Mitigations**: Penalty-based knowledge decay and configurable ingestion queue limits.
- **LLM Provider Orchestration**: Lazy-pull support for missing Ollama models during synthesis.
- **Binary Ingestion Sanitizer**: Proactive detection of base64 "brain rot", stripping images (with metadata extraction), and text extraction from embedded PDFs.
- **Latent Space Abstraction (LSA)**: 3-Stage retrieval (Surgical → Broad → Analogous) to bridge knowledge gaps and prevent hallucinations.
- **Consolidation Engine**: Background synthesis to merge conflicting facts and prune obsolete data.
- **Cognee Integration**: Native graph-based memory and context extraction.
- **Performance Tiers**: Hybrid `CHUNKS`/`GRAPH` search with sub-10ms L1 caching and sub-50ms SQLite-backed L2 bypass.
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
| `/v1/seed` | `POST` | Authoritative ingestion with **Job Tracking** (v2.0) and **Direct Fallback** (v1.9). |
| `/v1/seed/status` | `GET` | Poll for explicit success/failure of a `job_id`. |
| `/v1/sync` | `POST` | Sync OpenClaw session logs for an agent. |
| `/v1/consolidate` | `POST` | Trigger background knowledge synthesis pass. |
| `/v1/context/bulk-dispute` | `POST` | Selectively hide nodes matching a search query. |
| `/v1/tools/stats/{id}` | `GET` | Retrieve tool reliability metrics. |

## Documentation
- [Architecture Overview](docs/architecture.md)
- [Configuration Reference](docs/configuration.md)
- [API Contracts](docs/api_contracts.md)
- [Implementation Walkthrough](docs/walkthrough.md)

## License
MIT

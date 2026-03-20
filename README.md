# Thalamus

Universal Memory Middleware for OpenClaw and Cognee.

## Features
- **Decoupled Architecture**: Thin OpenClaw plugin + Rich Python middleware.
- **Evolutionary Knowledge Hub**: Automated feedback loop that rewards successful facts and penalizes "brain rot" based on real-world outcomes.
- **Latent Space Abstraction (LSA)**: 3-Stage retrieval (Surgical → Broad → Analogous) to bridge knowledge gaps and prevent hallucinations.
- **Authoritative Web Seeding**: Bulk-ingest documentation, PDFs, and raw code directly into the graph.
- **Consolidation Engine**: Background synthesis to merge conflicting facts and prune obsolete data.
- **Cognee Integration**: Native graph-based memory and context extraction.
- **Tool Reliability Ranking**: SQLite-backed tracking of tool success/failure to guide agent behavior.
- **Webhook Pipeline**: Real-time events (`MEMORIES_PUSHED`, `MEMORIES_SYNCED`) for ecosystem observability.

## Quick Start

1. **Install Dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Copy `config.json.example` to `config.json` and set your `OLLAMA_API_BASE` and `SESSIONS_DIR`.

3. **Run**:
   ```bash
   python -m src.thalamus.main
   ```
   Server starts at `http://127.0.0.1:8080`.

## API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/context` | `GET` | Fetches formatted context block (cached). |
| `/v1/ingest` | `POST` | Manually ingest message turns into the graph. |
| `/v1/sync` | `POST` | Sync OpenClaw session logs for an agent. |
| `/v1/search` | `POST` | Low-level graph search. |
| `/v1/tools/stats/{id}` | `GET` | Retrieve tool reliability metrics. |

## Documentation
- [Architecture Overview](docs/architecture.md)
- [API Contracts](docs/api_contracts.md)
- [Implementation Walkthrough](docs/walkthrough.md)

## License
MIT

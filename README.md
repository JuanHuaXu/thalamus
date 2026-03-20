# Thalamus

Universal Memory Middleware for OpenClaw and Cognee.

## Features
- **Decoupled Architecture**: Thin OpenClaw plugin + Rich Python middleware.
- **Cognee Integration**: Native graph-based memory and context extraction.
- **Context Caching**: High-performance TTL-based LRU cache to reduce latency.
- **Session Sync**: Automating fact mining by crawling OpenClaw's local session logs.
- **Tool Reliability Ranking**: SQLite-backed tracking of tool success/failure to guide agent behavior.
- **Webhook Pipeline**: Real-time events (`MEMORIES_PUSHED`, `MEMORIES_SYNCED`) for ecosystem observability.
- **Security**: Basic response sanitization and Bearer-token authentication.

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

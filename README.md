# Thalamus

Universal Memory Middleware for OpenClaw and Cognee.

## Overview
Thalamus acts as a "Relay Station" and "Memory Gardener" between the OpenClaw plugin and the Cognee Knowledge Graph backend.

## Features
- **Decoupled Architecture**: Thin OpenClaw plugin + Rich Python middleware.
- **Cognee Integration**: Leveraging Cognee for graph-based memory and context extraction.
- **LRU Caching**: High-performance context caching with TTL-based expiration and manual invalidation.
- **Prompt Injection Protection**: Sanitization of memory outputs to prevent LLM breakout.
- **Session Sync**: Capability to crawl and ingest existing OpenClaw session logs.

## Installation

1. Clone this repository into your Projects directory:
   ```bash
   git clone <repository-url> thalamus
   cd thalamus
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure the middleware (see `config.json` or environment variables).

## Running the Middleware

Start the FastAPI server:
```bash
python -m src.thalamus.main
```
By default, it runs on `http://127.0.0.1:8080`.

## API Endpoints

- `GET /v1/context`: Retrieve formatted context for a query.
- `POST /v1/ingest`: Ingest new messages into memory.
- `POST /v1/search`: Perform a manual search.
- `POST /v1/sync`: Sync OpenClaw sessions into the Cognee graph.

## Documentation
- [Architecture Overview](docs/architecture.md)
- [API Contracts](docs/api_contracts.md)
- [Implementation Walkthrough](docs/walkthrough.md)

## License
MIT

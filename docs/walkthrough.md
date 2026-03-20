# Implementation Walkthrough: Thalamus Memory System

I've successfully implemented a streamlined long-term memory system called **Thalamus**. It bridges the **OpenClaw (TypeScript)** ecosystem with the **Cognee (Python/Graph)** engine.

## 🏗️ The Architecture
Thalamus follows a "Thin Plugin + Intelligent Middleware" model. This allows OpenClaw to remain stable while the heavy lifting of memory ingestion and search is handled in Python.

### 1. Thalamus Middleware (Python/FastAPI)
Acts as the central relay station:
- **Location**: `/Users/clawdius/Projects/thalamus/`
- **Key File**: `src/thalamus/main.py`
- **Features**:
    - **Context Recall**: `/v1/context` fetches Graph nodes from Cognee and formats them for the agent.
    - **LRU Caching**: Prompt-level context is cached with TTL to reduce latency.
    - **Session Sync**: `/v1/sync` allows crawling OpenClaw session files to ingest facts post-conversation.
    - **Webhooks**: Outbound notifications for `MEMORIES_PUSHED` and `MEMORIES_SYNCED`.

### 2. Thalamus OpenClaw Plugin (TypeScript)
Acts as the lightweight bridge:
- **Location**: `/Users/clawdius/.openclaw/extensions/thalamus/`
- **Hooks**:
    - **Recall**: Fetches context from Thalamus *before* the agent starts.
    - **Capture**: Sends conversation turns to Thalamus *after* the agent ends.

---

## ⚡ How it works in practice

### A. Automatic Memory Injection (Recall)
When a user sends a prompt, the plugin calls `GET /v1/context`. Thalamus checks its local LRU cache. If not found, it queries Cognee for the most relevant graph nodes and returns them in a sanitized `<relevant-memories>` block.

### B. Proactive Memory Capture (Ingestion)
After the conversation turn ends, the plugin sends the latest messages to `POST /v1/ingest`. Thalamus pushes these to Cognee for graph processing and invalidates the local cache for that agent to ensure the next recall is fresh.

### C. Backend Fact Mining (Sync)
The `/v1/sync` endpoint can be triggered to read raw `.jsonl` session files directly from the OpenClaw data directory. This allows the system to build or restore the knowledge graph from past conversations.

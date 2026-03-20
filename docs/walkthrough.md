# Implementation Walkthrough: Thalamus Memory System

I've successfully implemented a state-of-the-art long-term memory system called **Thalamus**. It bridges the **OpenClaw (TypeScript)** ecosystem with the **Cognee (Python/Graph)** engine via a decoupled middleware.

## 🏗️ The Architecture
We moved away from a hardcoded integration to a "Thin Plugin + Intelligent Middleware" model.

### 1. Thalamus Middleware (Python/FastAPI)
Acts as the "Brain's Relay Station."
- **Location**: `/Users/clawdius/Projects/thalamus/`
- **Key File**: `src/thalamus/main.py`
- **Features**:
    - **Context Generation**: `/v1/context` fetches graph nodes from Cognee and formats them for the agent.
    - **LRU Caching**: Prompt-level context is cached with TTL to reduce latency and Cognee compute.
    - **Session Sync**: `/v1/sync` allows Thalamus to crawl OpenClaw session files and mine them for facts post-conversation.
    - **Webhooks**: Outbound notifications for `MEMORIES_PUSHED` and `MEMORIES_SYNCED`.
    - **Hybrid Storage**: Tracks tool reliability in a local SQLite database while facts live in the Cognee graph.

### 2. Thalamus OpenClaw Plugin (TypeScript)
Acts as the "Thin Client Bridge."
- **Location**: `/Users/clawdius/.openclaw/extensions/thalamus/`
- **Hooks**:
    - **Auto-Recall**: Fetches context from Thalamus *before* the agent starts.
    - **Auto-Capture**: Sends conversation turns to Thalamus *after* the agent ends.

---

## ⚡ How it works in practice

### A. Automatic Memory Injection (Recall)
When a user sends a prompt, the plugin calls Thalamus:
1.  **Plugin** hits `GET /v1/context`.
2.  **Thalamus** checks its **LRU Cache**.
3.  If miss, **Thalamus** queries **Cognee** (GRAPH Search).
4.  **Thalamus** sanitizes the output (Injection Protection) and returns it to OpenClaw.

### B. Proactive Memory Capture (Ingestion)
After the conversation turn ends:
1.  **Plugin** hits `POST /v1/ingest`.
2.  **Thalamus** writes to **Cognee** and **SQLite**.
3.  **Thalamus** invalidates the internal cache for that agent.
4.  **Thalamus** fires a **Webhook** to external observers.

### C. Background Fact Mining (Sync)
1.  **System/User** hits `POST /v1/sync`.
2.  **Thalamus** reads raw `.jsonl` session files from the OpenClaw data directory.
3.  **Thalamus** extracts message turns and "cognifies" them into the permanent graph.

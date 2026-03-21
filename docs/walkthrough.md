# Implementation Walkthrough: Thalamus Memory System

I've successfully implemented a streamlined long-term memory system called **Thalamus**. It bridges the **OpenClaw (TypeScript)** ecosystem with the **Cognee (Python/Graph)** engine.

## 🏗️ The Architecture
Thalamus follows a "Thin Plugin + Intelligent Middleware" model. This allows OpenClaw to remain stable while the heavy lifting of memory ingestion and search is handled in Python.

### 1. Thalamus Middleware (Python/FastAPI)
Acts as the central relay station:
- **Location**: `/Users/clawdius/Projects/thalamus/`
- **Key File**: `src/thalamus/main.py`
- **Features**:
    - **Context Recall**: `/v1/context` fetches Graph nodes from Cognee and ranks tools by reliability from SQLite.
    - **Configuration Management**: Centralized `config.json` for hot-swapping providers and thresholds.
    - **LRU Caching**: Prompt-level context is cached with TTL to reduce latency.
    - **Session Sync**: `/v1/sync` allows crawling OpenClaw session files to ingest facts post-conversation.
    - **Webhooks**: Outbound notifications for `MEMORIES_PUSHED` and `MEMORIES_SYNCED`.
    - **Relational Storage**: High-performance persistence for tool reliability and performance metrics via SQLite.
    - **Instrumented Worker**: Background process for ingestion, seeding, and building knowledge graphs via `cognify`.
### Verification Results
The Evolutionary Knowledge Hub has been verified using a dedicated test suite (`tests/test_evolution.py`).

| Feature | Test Case | Status | Rationale |
|---------|-----------|--------|-----------|
| **Web Seeding** | `test_crawler_extraction` | ✅ PASSED | Verified `trafilatura` high-fidelity extraction. |
| **Feedback Loop** | `test_fact_reputation_dispute_api` | ✅ PASSED | Automated 'failure' detection successfully penalizes nodes. |
| **Knowledge Filtering** | `test_disputed_fact_filtering` | ✅ PASSED | 'DISPUTED' nodes are strictly hidden from agent context. |

> [!TIP]
> Run the suite yourself using: `PYTHONPATH=src python3 -m pytest tests/test_evolution.py`
### 4. Evolutionary Knowledge Hub (New)
The system now manages its own "Scientific Method" for truth:

1.  **Authoritative Seeding**:
    `curl -X POST http://localhost:8000/v1/seed -d '{"urls": ["https://docs.cognee.ai"]}'`
    -   *Logic*: Extract clean text from docs and prime the Knowledge Graph.

> [!IMPORTANT]
> **Real-Time Ingestion**: Thalamus is a live memory system. Once seeding completes, facts are **immediately** available to the agent. **No gateway or agent restart is required.**

2.  **Automated Feedback Loop**:
    When an agent turn ends, Thalamus automatically detects success or failure.
    -   *Success*: `{"role": "assistant", "content": "Correct! It worked."}` -> Increments confidence in used nodes.
    -   *Failure*: `{"role": "assistant", "content": "Error: Command not found."}` -> Node reputation drops. 
    -   *Dispute*: After 3 failures, a node is marked as `DISPUTED` and **filtered out** of future contexts.

### 3. Consolidation Engine
Trigger a consolidation pass to synthesize conflicting facts and prune obsolete data.

```bash
curl -X POST http://localhost:8080/v1/consolidate \
     -H "Content-Type: application/json" \
     -d '{"agent_id": "scientific_agent"}'
```

### 4. Seeding Undo (The "Self-Correct" Switch)
In addition to automated feedback, you can manually "undo" an entire seeding session if you realize the source was low quality. This archives the facts for that agent.

```bash
curl -X POST http://localhost:8080/v1/seed/undo \
     -H "Content-Type: application/json" \
     -d '{"agent_id": "undo_test_agent"}'
```

---

### 5. Selective Pruning (Bulk Dispute)
If you accidentally ingest low-quality data (like a large base64 image or internal boilerplate), you can selectively "dispute" it based on a search query. This instantly hides the matching nodes from the agent's memory.

```bash
curl -X POST http://localhost:8080/v1/context/bulk-dispute \
     -H "Content-Type: application/json" \
     -d '{
       "agent_id": "my_agent",
       "query": "base64_image_data_snippet",
       "limit": 50
     }'
```

---

### 6. Surgical Garbage Collection (Compaction)
Physically removes only the "disputed" metadata from SQLite. This "forgets" the mistake permanently at the middleware level without touching your other valid memories.

```bash
curl -X POST http://localhost:8080/v1/context/compact \
     -H "Content-Type: application/json" \
     -d '{
       "agent_id": "my_agent",
       "status_filter": "DISPUTED"
     }'
```

---

### 7. Physical Memory Purge (Hard Reset)
The "Nuclear Option". Permanently removes all traces of an agent's memory (chat logs and seeds) from Cognee and SQLite. Use this to reclaim space or wipe sensitive mistakes.

```bash
curl -X DELETE http://localhost:8080/v1/context/purge \
     -H "Content-Type: application/json" \
     -d '{
       "agent_id": "my_agent",
       "confirm": true
     }'
```
### 2. Thalamus OpenClaw Plugin (TypeScript)
Acts as the lightweight bridge:
- **Location**: `/Users/clawdius/.openclaw/extensions/thalamus/`
- **Hooks**:
    - **Recall**: Fetches context from Thalamus *before* the agent starts.
    - **Capture**: Sends conversation turns to Thalamus *after* the agent ends.

### D. Latent Space Abstraction (LSA)
To prevent hallucinations when specific knowledge is missing, Thalamus implements a **3-Stage Retrieval Pipeline**:

1.  **Surgical Search**: First, it searches only the agent's partitioned datasets.
2.  **Broad Fallback**: If no specific facts are found, it broadens the search to the **Global Graph** (all synced agents and documentation).
3.  **Analogous Expansion**: If still empty, it applies **Heuristic Query Mutation** (e.g. stripping version numbers or specific constraints) to find analogous concepts in other domains.

These latent facts are tagged with `<latent-abstraction>` in the prompt to signal to the agent that it should reason by analogy rather than memory.

> [!NOTE]
> **Processing Latency**: After seeding large documents (like PDFs), the graph "cognification" process can take several minutes. During this window, search queries may experience higher latency or timeouts as the graph is updated.

---

## ⚡ How it works in practice

### A. Automatic Memory Injection (Recall)
When a user sends a prompt, the plugin calls `GET /v1/context`. Thalamus checks its local LRU cache. If not found, it queries Cognee for the most relevant graph nodes and returns them in a sanitized `<relevant-memories>` block.

### B. Proactive Memory Capture (Ingestion)
After the conversation turn ends, the plugin sends the latest messages to `POST /v1/ingest`. Thalamus pushes these to Cognee for graph processing and invalidates the local cache for that agent to ensure the next recall is fresh.

### C. Backend Fact Mining (Sync)
The `/v1/sync` endpoint can be triggered to read raw `.jsonl` session files directly from the OpenClaw data directory. This allows the system to build or restore the knowledge graph from past conversations.

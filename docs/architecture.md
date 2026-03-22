# TADD: OpenClaw + Cognee "Universal Middleware" Architecture

## 1. Overview
This document outlines the migration from a **hardcoded built-in** Cognee integration to a **modular, middleware-first** approach. The goal is to move the core intelligence (graph reasoning, caching, and cleaning) into a standalone Python service, leaving the OpenClaw integration as a stable, lightweight bridge.

---

## 2. System Architecture
Thalamus acts as the "Cognitive Traffic Controller" and **Evolutionary Knowledge Hub** between OpenClaw and Cognee.

```mermaid
graph TD
    subgraph "OpenClaw (Typescript)"
        OC_P["Thin Plugin"]
    end
    
    subgraph "Middleware Service (Python/FastAPI)"
        MW["Thalamus Middleware"]
        TG["Topic Guard (Semantic Vetting)"]
        L1["L1: In-Memory Cache (RAM)"]
        L2["L2: Persistent Cache (SQLite)"]
        Consol["Consolidation Engine"]
    end
    
    subgraph "Data Layer"
        CG["Cognee (Knowledge Graph)"]
        SL["SQLite (Fact Rep + Job Registry)"]
    end

    OC_P -- "JSON API" --> MW
    MW --> TG
    TG --> L1
    TG --> L2
    MW -- "Seed / Fetch" --> Web["Web Docs"]
    MW --> CG
    MW --> SL
```

### 📡 Event Pipeline
Thalamus notifies external services via webhooks when data is processed:
-   **MEMORIES_PUSHED**: Fired when new message turns are ingested via `/v1/ingest`.
-   **MEMORIES_SYNCED**: Fired when session logs are crawled via `/v1/sync`.

### 🧠 Evolutionary Knowledge (SQLite)
Thalamus uses a local SQLite database to manage the **lifecycle** of facts stored in Cognee.
-   **Fact Reputation**: Every interaction weights the "confidence" of a graph node. High-failure nodes are eventually "hidden" from the agent.
-   **Temporal Decay**: Passive "forgetting" of stale information that hasn't been accessed or reinforced in recent interaction cycles.

---

## 3. Sequence: Evolutionary Data Flow

```mermaid
sequenceDiagram
    participant OC as OpenClaw
    participant MW as Thalamus
    participant CG as Cognee
    participant SL as SQLite (Reputation)
    participant CE as Consolidator
    
    Note over OC,MW: Stage 1: Contextual Recall (Parallel Race Car)
    OC->>MW: GET /v1/context
    MW->>MW: Check L1 Cache (RAM)
    MW-->>OC: [Hit] Return Context (~8ms)
    
    MW->>SL: L2 Cache: Check persistent_context_cache
    MW-->>OC: [Hit] Return Context (~45ms)

    Note right of MW: Cache MISS: Multi-Dataset Parallel Search
    par Step 1: Broad Memory Search
        MW->>CG: Search 'agent_{id}' (CHUNKS)
    and Step 2: Documentation Search
        MW->>CG: Search 'doc_seed_{id}' (CHUNKS)
    and Step 3: Global Expansion
        MW->>CG: Search default graph (FALLBACK)
    end
    
    Note right of MW: Hard 25s Timeout Orchestration
    
    MW->>SL: Get Fact Reputation scores
    MW->>MW: De-duplicate & Filter nodes
    MW->>SL: Populate L2 Cache
    MW->>MW: Populate L1 Cache
    MW-->>OC: Return Vetted Context + <latent-abstraction>
    
    Note over OC,MW: Stage 2: Memory Capture & Feedback
    OC->>MW: POST /v1/ingest
    MW->>CG: Ingest raw facts
    MW->>SL: Increment success/failure for used nodes
    MW-->>OC: 200 OK
    
    Note over CE,CG: Stage 3: Consolidation (Background)
    CE->>CG: Scan for conflicting node clusters
    CE->>SL: Review interaction history
    CE->>CE: Synthesize "Composite Truth"
    CE->>CG: Replace/Prune old nodes
```

---

## 4. Implementation Details

### A. Fact Consolidation
-   **Synthesis**: Periodic passes merge redundant or conflicting nodes into high-confidence "wisdom" nodes using the agent's historical performance as a guide.
-   **Conflict Resolution**: Empirical truth (terminal success) always out-ranks seeded documentation when conflicts arise in SQLite.

### B. Output Sanitization & Freshness
-   **Tag Stripping**: Prevents prompt injection breakouts.
-   **Freshness Weighting**: Natural decay ensures that older, un-reinforced knowledge drifts into "Historical Cold Storage."

---

## 5. Dynamic Scaling & Mitigations
Thalamus is designed to handle high-volume streams by implementing proactive mitigations:
- **Penalty-based Decay**: Nodes that cause agent failures receive a "Penalty" to their `dynamic_threshold`. This makes them increasingly likely to be filtered out of future context until they are either "Reset" (by success) or Archived.
- **Queue Buffering**: Memory ingestion and seeding tasks are processed via an asynchronous `asyncio.Queue` with a configurable `maxsize` to prevent memory exhaustion during bulk operations.

## 6. LLM Provider Orchestration
The synthesis engine handles LLM provider availability through a "Lazy-Pull" mechanism:
- **Auto-Pull**: If the configured Ollama model (e.g., `qwen3.5:9b`) is missing from the LAN provider, Thalamus automatically triggers a pull before continuing the synthesis pass.
- **Robust Joining**: Provider URLs are handled robustly to ensure compatibility with various endpoint configurations (e.g., trailing slashes).

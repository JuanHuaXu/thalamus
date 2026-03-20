# TADD: OpenClaw + Cognee "Universal Middleware" Architecture

## 1. Overview
This document outlines the migration from a **hardcoded built-in** Cognee integration to a **modular, middleware-first** approach. The goal is to move the core intelligence (graph reasoning, caching, and cleaning) into a standalone Python service, leaving the OpenClaw integration as a stable, lightweight bridge.

---

## 2. Current State (Built-in Integration)
Currently, Cognee is integrated directly into the OpenClaw core. This is difficult to maintain and lacks advanced features like caching or hybrid search.

```mermaid
graph TD
    subgraph "OpenClaw Core (Typescript)"
        SM["Search Manager (Hardcoded)"]
        MT["Memory Tools"]
    end
    
    subgraph "Cognee Server (Python)"
        API["Default /api/v1/search"]
        Graph["Raw Knowledge Graph"]
    end

    MT --> SM
    SM -- "Basic Vector Search" --> API
    API --> Graph
```

---

## 3. Proposed State (The Universal Vision)
The new vision introduces a **Standalone Middleware** (Thalamus) that acts as a "Traffic Controller" and a **Hybrid Data Layer**.

```mermaid
graph TD
    subgraph "OpenClaw (Typescript)"
        OC_P["Thin Plugin (Stable)"]
    end
    
    subgraph "Middleware Service (Python/FastAPI)"
        MW["Thalamus Middleware"]
        Cache["2-Layer Cache (Redis/LRU)"]
        Logic["Cleaning / Re-ranking / Temporal"]
    end
    
    subgraph "Hybrid Data Layer (Modular)"
        CG["Cognee (Knowledge Graph)"]
        PG["PostgreSQL (RDBMS - Stubbed)"]
    end

    OC_P -- "JSON API (Push)" --> MW
    MW -- "File Read (Pull)" --> Sessions
    MW --> Cache
    MW -- "Event Notification" --> Webhooks["External Webhooks (Outbound)"]
    MW -- "Reasoning/Semantic" --> CG
    MW -- "Structured/Logs (Future)" --> PG
```

### 📡 The "Event-Driven" Webhook Layer
Thalamus is no longer a passive relay; it proactively notifies the ecosystem when internal state changes.
-   **MEMORIES_SYNCED**: Fired when a session `sync` or `ingest` is complete.
-   **FACT_EXTRACTED**: Fired when a high-importance fact (user preference) is discovered.
-   **GRAPH_UPDATED**: Fired when Cognee finishes its background reorganization.

### 🧠 The "Pull-based Sync" (Middleware-Led Intelligence)
Instead of relying on OpenClaw to decide what is "important," Thalamus can now **pull** raw session data directly from OpenClaw's filesystem.
-   **Why**: OpenClaw's native memory filters are often too aggressive or too noisy. Thalamus can use more expensive, intelligent models to "mine" facts from raw logs in the background.
-   **How**: Thalamus monitors the `.jsonl` session files, extracts atomic facts, and "cognifies" them into a coherent graph.

### Why this architecture?
1.  **Total Decoupling**: Changes to Cognee's internal API never break the OpenClaw plugin.
2.  **Hybrid Power**: Combines Cognee's graph reasoning with high-speed Metadata filtering.
3.  **Stability**: The OpenClaw plugin becomes a tiny, unchanging bridge.

---

## 4. Sequence: Middleware Data Flow

```mermaid
sequenceDiagram
    participant OC as OpenClaw (Thin)
    participant MW as Thalamus (Logic)
    participant CG as Cognee (Graph)
    participant PG as PostgreSQL (RDBMS)
    
    rect rgb(230, 240, 255)
    Note over OC,MW: Stage 1: Contextual Recall (before_agent_start)
    OC->>MW: "What do we know about 'Project X'?"
    MW->>MW: Check Cache (Fast Hit)
    MW->>CG: Parallel Graph Search
    MW->>PG: Parallel Keyword/Vector Search
    MW->>MW: Re-rank + Add [Freshness] Tags
    MW-->>OC: "Here is the summary of Project X..."
    end
    
    rect rgb(250, 235, 235)
    Note over OC,MW: Stage 2: Memory Capture (agent_end)
    OC->>MW: "User said they prefer Dark Mode."
    MW->>MW: Noise Filter (Skip small talk)
    MW->>MW: Deduplicate against PG
    MW->>PG: Log Session Intent
    MW->>CG: Ingest / Cognify (Build Fact Node)
    end
```

---

## 5. Memory Management Strategies

### A. Advanced Search & Optimization
-   **Hybrid Parallel Search**: Concurrent Vector, Keyword, and Graph queries.
-   **2-Layer Caching**: Prompt-level and Embedding-level caching.

### B. Memory Sanitization (The "Gardener")
-   **Duplicate Detection**: High-threshold similarity check prevents redundant nodes.
-   **Noise Filtering**: LLM-based classification drops "small talk".
-   **Conflict Resolution**: Detects when new info overwrites old info.

### C. Governance & Temporal Encoding
-   **Freshness Markers**: Context is tagged with `[Current]`, `[Stale]`, or `[Historical]`.
-   **Importance Weighting**: High-signal facts are prioritized.
-   **Privacy Redaction**: Automated scrubbing of API keys and PII.
-   **Provenance**: Every memory traces back to its original session.

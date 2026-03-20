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

## 3. System Architecture
The architecture utilizes a **Standalone Middleware** (Thalamus) that acts as a bridge between OpenClaw and Cognee.

```mermaid
graph TD
    subgraph "OpenClaw (Typescript)"
        OC_P["Thin Plugin"]
    end
    
    subgraph "Middleware Service (Python/FastAPI)"
        MW["Thalamus Middleware"]
        Cache["LRU Cache"]
    end
    
    subgraph "Data Layer"
        CG["Cognee (Knowledge Graph)"]
        PG["SQLite (Stats)"]
    end

    OC_P -- "JSON API" --> MW
    MW -- "File Read (Sync)" --> Sessions
    MW --> Cache
    MW -- "Webhooks" --> Webhooks["External Webhooks"]
    MW --> CG
    MW --> PG
```

### 📡 Event Pipeline
Thalamus notifies external services via webhooks when data is processed:
-   **MEMORIES_PUSHED**: Fired when message turns are ingested via `/v1/ingest`.
-   **MEMORIES_SYNCED**: Fired when session logs are crawled via `/v1/sync`.

### 🧠 Session Synchronization
Thalamus can **pull** raw session data directly from OpenClaw's filesystem.
-   **How**: The `/v1/sync` endpoint reads `.jsonl` session files from the OpenClaw data directory and ingests them into the Cognee graph.
-   **Benefit**: Allows for rebuilding or expanding the knowledge graph from historical data without relying on real-time capture.

### Why this architecture?
1.  **Isolation**: Changes to Cognee's internal API are handled within the middleware.
2.  **Performance**: The LRU cache provides high-speed recall for repeated queries.
3.  **Observability**: Webhooks and tool stats provide visibility into memory performance.

---

## 4. Sequence: Data Flow

```mermaid
sequenceDiagram
    participant OC as OpenClaw
    participant MW as Thalamus
    participant CG as Cognee
    
    Note over OC,MW: Stage 1: Contextual Recall
    OC->>MW: GET /v1/context
    MW->>MW: Check LRU Cache
    MW->>CG: Search Graph
    MW-->>OC: Return <relevant-memories> block
    
    Note over OC,MW: Stage 2: Memory Capture
    OC->>MW: POST /v1/ingest
    MW->>CG: Ingest / Cognify
    MW->>MW: Invalidate Cache
    MW-->>OC: 200 OK
```

---

## 5. Implementation Details

### A. Context Caching
-   **LRU Cache**: A simple time-to-live (TTL) cache prevents redundant graph searches for the same query during a session.
-   **Invalidation**: Ingesting new memories automatically clears the cache for the relevant agent to ensure freshness.

### B. Output Sanitization
-   **Tag Stripping**: To prevent prompt injection, Thalamus strips any nested `<relevant-memories>` or `<external-content>` tags from the memories before returning them to OpenClaw.

### C. Reliability Tracking
-   **Tool Stats**: Records tool execution events in a local SQLite database to track reliability over time.

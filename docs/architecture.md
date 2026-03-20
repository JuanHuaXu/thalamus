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
        Cache["LRU Cache"]
        Consol["Consolidation Engine"]
    end
    
    subgraph "Data Layer"
        CG["Cognee (Knowledge Graph)"]
        SL["SQLite (Fact Reputation)"]
    end

    OC_P -- "JSON API" --> MW
    MW -- "File Read (Sync)" --> Sessions
    MW --> Cache
    MW -- "Seed / Fetch" --> Web["Web Docs"]
    MW --> CG
    MW --> SL
    Consol -- "Synthesis / Pruning" --> CG
    Consol -- "Audit / Decay" --> SL
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
    
    Note over OC,MW: Stage 1: Contextual Recall (3-Stage LSA)
    OC->>MW: GET /v1/context
    MW->>MW: Check LRU Cache
    par Step 1: Surgical Search
        MW->>CG: Search Agent-Specific Dataset
    and Step 2: Broad Fallback
        MW->>CG: Search Global Graph (if Step 1 empty)
    and Step 3: Analogous Expansion
        MW->>CG: Mutate Query (if Step 1+2 empty)
    end
    MW->>SL: Get Fact Reputation scores
    MW->>MW: Filter out "Brain Rot" (low-trust nodes)
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

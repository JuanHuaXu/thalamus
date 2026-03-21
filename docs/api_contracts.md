# API Contracts: Thalamus Middleware

This document defines the interface between OpenClaw (TypeScript Plugin), the Thalamus Middleware (Python/FastAPI), and the Cognee Backend.

## 1. External API (OpenClaw <-> Thalamus)
These endpoints are exposed by the standalone Thalamus service for consumption by the OpenClaw TypeScript plugin.

### A. Contextual Recall
Used in the `before_agent_start` hook to inject graph knowledge into the prompt.
-   **Endpoint**: `GET /v1/context`
-   **Query Params**:
    -   `q`: (string) The user's current prompt.
    -   `agent_id`: (string) Unique ID of the agent session.
-   **Response** (200 OK):
    ```json
    {
      "context": "string",
      "metadata": { 
        "nodes_found": 5, 
        "nodes_vetted": 2, 
        "latent_nodes": 3,
        "lsa_triggered": true 
      }
    }
    ```

### B. Knowledge Seeding (Evolutionary)
Authoritative ingestion of documentation directly into the Graph.
-   **Endpoint**: `POST /v1/seed`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "urls": ["string"]
    }
    ```
-   **Response** (202 Accepted): { "status": "queued", "urls_submitted": 1 }

### C. Resource Consolidation
Triggers the background synthesis of conflicting or redundant facts.
-   **Endpoint**: `POST /v1/consolidate`
-   **Query Params**:
    -   `agent_id`: (string) Filter for a specific agent pass.
-   **Response**: { "status": "success", "nodes_processed": 5 }

### D. Selective Memory Pruning (Bulk Dispute)
Instantly hides nodes matching a search query from an agent's future context.
-   **Endpoint**: `POST /v1/context/bulk-dispute`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "query": "string",
      "limit": 20
    }
    ```
-   **Response**: { "status": "success", "nodes_hidden": 5, "query": "string" }

### E. Seeding Undo
Reverses a seeding operation for a specific agent by archiving facts.
-   **Endpoint**: `POST /v1/seed/undo`
-   **Body**: { "agent_id": "string" }
-   **Response**: { "status": "success", "action": "ARCHIVED" }

### F. Surgical Garbage Collection (Compaction)
Physically deletes only facts with a specific status (default: `DISPUTED`) from SQLite.
-   **Endpoint**: `POST /v1/context/compact`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "status_filter": "DISPUTED"
    }
    ```
-   **Response**: { "status": "success", "message": "Surgical compaction completed.", "agent_id": "string" }

### G. Physical Memory Purge (Hard Reset)
Permanently deletes all graph data and reputation scores for an agent.
-   **Endpoint**: `DELETE /v1/context/purge`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "confirm": true
    }
    ```
-   **Response**: { "status": "success", "agent_id": "string", "cognee_datasets_deleted": 1 }

### D. Message Ingestion
Used in the `agent_end` hook to send new conversation data to the graph.
-   **Endpoint**: `POST /v1/ingest`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "conversation_id": "string",
      "messages": [
        { "role": "user", "content": "string" },
        { "role": "assistant", "content": "string" }
      ]
    }
    ```
-   **Response**: { "status": "success", "message": "Memory ingested." }

### E. Session Sync (Pull)
Manually triggers a scan of OpenClaw's local session directory.
-   **Endpoint**: `POST /v1/sync`
-   **Body**: { "agent_id": "string", "session_id": "string" }
-   **Response**: { "status": "success", "messages_synced": 100 }

### F. Manual Search
Perform a direct search on the memory graph.
-   **Endpoint**: `POST /v1/search`
-   **Body**: { "query": "string", "limit": 5 }
-   **Response**:
    ```json
    [
      { "snippet": "string", "score": 0.95, "category": "string" }
    ]
    ```

### G. Tool Reliability Stats
Retrieve historical reliability for tools bound to an agent.
-   **Endpoint**: `GET /v1/tools/stats/{agent_id}`
-   **Response**:
    ```json
    {
      "agent_id": "string",
      "stats": [
        { "tool_name": "string", "successes": 10, "failures": 1 }
      ]
    }
    ```

## 2. Webhook Notifications (Outbound)
Sent from Thalamus to configured `webhook_urls`.
-   **Endpoint**: `POST [configured_url]`
-   **Events**: `MEMORIES_PUSHED`, `MEMORIES_SYNCED`
-   **Payload**:
    ```json
    {
      "event": "string",
      "agent_id": "string",
      "payload": { "messages_count": 5 }
    }
    ```

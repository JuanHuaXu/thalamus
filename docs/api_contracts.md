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
      "context": "<relevant-memories>\n1. [preference] User prefers dark mode.\n2. [fact] Project X is a TypeScript app.\n</relevant-memories>",
      "metadata": { "nodes_found": 2, "latency_ms": 140 }
    }
    ```

### B. Message Ingestion
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
-   **Response** (200 OK):
    ```json
    { "status": "success", "message": "Memory ingested and cache invalidated." }
    ```

### C. Session Sync (Pull)
Manually triggers a scan of OpenClaw's local session directory for a specific agent.
-   **Endpoint**: `POST /v1/sync`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "session_id": "string"  // Optional: Sync only one session
    }
    ```
-   **Response** (200 OK):
    ```json
    { 
      "status": "success", 
      "messages_synced": 150, 
      "new_facts_extracted": 0,
      "sessions_scanned": 5
    }
    ```

## 3. Webhook Notifications (Outbound)
Sent from Thalamus to configured `webhook_urls`.

### A. Generic Event Payload
-   **Method**: `POST`
-   **Body**:
    ```json
    {
      "event": "MEMORIES_PUSHED | MEMORIES_SYNCED",
      "agent_id": "string",
      "timestamp": 123456789,
      "payload": {
        "messages_count": 5,
        "sessions_scanned": 1
      }
    }
    ```

### D. Manual Search
Perform a direct search on the memory graph.
-   **Endpoint**: `POST /v1/search`
-   **Body**:
    ```json
    {
      "query": "string",
      "limit": 5
    }
    ```
-   **Response** (200 OK):
    ```json
    [
      {
        "snippet": "Recall content...",
        "score": 0.95,
        "category": "preference"
      }
    ]
    ```

### E. Tool Reliability Stats
Retrieve historical reliability for tools bound to an agent.
-   **Endpoint**: `GET /v1/tools/stats/{agent_id}`
-   **Response** (200 OK):
    ```json
    {
      "agent_id": "string",
      "stats": [
        { "tool_name": "searxng_search", "success_count": 10, "failure_count": 1, "last_error": null }
      ]
    }
    ```

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
-   **Response** (202 Accepted):
    ```json
    { "status": "queued", "task_id": "uuid" }
    ```

### C. Session Sync (Pull)
Manually triggers a scan of OpenClaw's local session directory for a specific agent.
-   **Endpoint**: `POST /v1/sync`
-   **Body**:
    ```json
    {
      "agent_id": "string",
      "session_id": "string",  // Optional: Sync only one session
      "deep_scan": false       // Optional: Use expensive LLM filtering
    }
    ```
-   **Response** (200 OK):
    ```json
    { "status": "success", "messages_synced": 150, "new_facts_extracted": 12 }
    ```

## 3. Webhook Notifications (Outbound)
Sent from Thalamus to configured `webhook_urls`.

### A. Generic Event Payload
-   **Method**: `POST`
-   **Body**:
    ```json
    {
      "event": "MEMORIES_SYNCED | FACT_EXTRACTED",
      "agent_id": "string",
      "timestamp": 123456789,
      "payload": {
        "count": 5,
        "message": "Cognification complete for agent main"
      }
    }
    ```

### C. Manual Search
Used by the `memory_search` tool for proactive agent-led recall.
-   **Endpoint**: `POST /v1/search`
-   **Body**:
    ```json
    {
      "query": "string",
      "limit": 5,
      "min_score": 0.5
    }
    ```
-   **Response** (200 OK):
    ```json
    [
      {
        "path": "memory:graph-node-id",
        "snippet": "...",
        "score": 0.95,
        "category": "preference"
      }
    ]
    ```

---

## 2. Internal API (Thalamus <-> Cognee)
The Middleware translates the requests above into native Cognee API calls.

### A. Search
-   **Endpoint**: `POST /api/v1/search`
-   **Body**: `{ "query": string, "search_type": "GRAPH", "limit": number }`

### B. Add (Ingestion)
-   **Endpoint**: `POST /api/v1/add`
-   **Type**: `multipart/form-data`
-   **Fields**:
    -   `data`: (File) Binary or text representation of the conversation.
    -   `datasetName`: (string) "default" or `agent_id`.

### C. Cognify (Processing)
-   **Endpoint**: `POST /api/v1/cognify`
-   **Body**: `{ "datasets": ["datasetName"] }`

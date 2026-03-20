from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from pathlib import Path
import json
import re
from cachetools import TTLCache
import httpx
import time
from .api.schemas import IngestRequest, SearchRequest, ContextResponse, SearchResult, SyncRequest, SyncResponse, MemoryMessage, ToolExecutionEvent, ToolStatsResponse
from .providers.cognee import CogneeProvider
from .providers.relational import SQLiteRelationalProvider
from .core.config import settings

# HTTP Bearer Auth
security = HTTPBearer(auto_error=False)

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if settings.api_key:
        if not credentials or credentials.credentials != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

app = FastAPI(title="Thalamus Middleware", version="0.1.0", dependencies=[Depends(verify_api_key)])

# Initialize providers
cognee = CogneeProvider()
rdbms = SQLiteRelationalProvider()

# LRU Cache for Context: Key = (agent_id, query)
context_cache = TTLCache(maxsize=1000, ttl=settings.cache_ttl_seconds)

async def broadcast_event(event_type: str, agent_id: str, payload: dict):
    # ... (rest of broadcast_event as before)
    pass

@app.get("/v1/context", response_model=ContextResponse)
async def get_context(q: str, agent_id: str):
    """
    Orchestrates search across multiple providers and returns a pre-formatted context block with caching.
    """
    cache_key = (agent_id, q)
    if cache_key in context_cache:
        print(f"[Thalamus] Cache hit for query: {q}")
        return context_cache[cache_key]

    try:
        # 1. Fetch memories from Cognee (with fail-soft)
        mem_results = []
        try:
            mem_results = await cognee.search(q, limit=5)
        except Exception as e:
            print(f"[Thalamus] Cognee search failed (continuing with tool stats): {e}")

        # 2. Fetch tool reliability stats from SQLite for ranking/briefing
        tool_stats = []
        try:
            tool_stats = await rdbms.get_tool_stats(agent_id)
        except Exception as e:
            print(f"[Thalamus] SQLite stats fetch failed: {e}")
        
        # Filter for tools that have actually been used and have stats
        active_tool_stats = [ts for ts in tool_stats if ts.successes > 0 or ts.failures > 0]
        # Rank by success rate: successes / (successes + failures)
        active_tool_stats.sort(key=lambda x: x.successes / (x.successes + x.failures) if (x.successes + x.failures) > 0 else 0, reverse=True)

        def sanitize_memory(text: str) -> str:
            # Strip out malicious closing tags to prevent prompt injection breakouts
            safe = re.sub(r'</relevant-memories>', '[tag removed]', text, flags=re.IGNORECASE)
            safe = re.sub(r'</tool-reliability>', '[tag removed]', safe, flags=re.IGNORECASE)
            return safe

        # Format Memory Block
        if mem_results:
            memory_list = "\n".join([
                f"- [{res.category or 'Memory'}] {sanitize_memory(res.snippet)}"
                for res in mem_results
            ])
            mem_block = f"<relevant-memories>\n{memory_list}\n</relevant-memories>"
        else:
            mem_block = "<relevant-memories>\nNo relevant memories found.\n</relevant-memories>"
            
        # Format Tool Reliability Block (Ranking)
        if active_tool_stats:
            stats_list = "\n".join([
                f"- {ts.tool_name}: {ts.successes} success, {ts.failures} failure (Reliability: {int((ts.successes / (ts.successes + ts.failures)) * 100)}%)"
                for ts in active_tool_stats
            ])
            tool_block = f"<tool-reliability>\nHistorical tool performance for this agent:\n{stats_list}\n</tool-reliability>"
        else:
            tool_block = ""
            
        combined_context = f"{mem_block}\n\n{tool_block}".strip()
        
        response = ContextResponse(
            context=combined_context,
            metadata={
                "nodes_found": len(mem_results), 
                "tools_ranked": len(active_tool_stats),
                "cached": False
            }
        )
        
        # Cache for subsequent calls
        context_cache[cache_key] = response
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/ingest")
async def ingest_memory(request: IngestRequest):
    """
    Ingests messages into both graph and relational backends.
    Invalidates the context cache for the agent to ensure 'Fresh' recall.
    """
    try:
        # Ingest to Cognee (Active)
        await cognee.add(request)
        
        # Ingest to RDBMS (Stub)
        await rdbms.add(request)
        
        # Temporal Invalidation: Clear any cached context for this agent
        # (Since cache_key is (agent_id, query), we clear all matching agent_id)
        keys_to_clear = [k for k in context_cache.keys() if k[0] == request.agent_id]
        for k in keys_to_clear:
            del context_cache[k]
            
        print(f"[Thalamus] Cache invalidated for agent: {request.agent_id}")
        
        # Notify via Webhook
        await broadcast_event("MEMORIES_PUSHED", request.agent_id, {"messages_count": len(request.messages)})
        
        return {"status": "success", "message": "Memory ingested and cache invalidated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/search", response_model=List[SearchResult])
async def manual_search(request: SearchRequest):
    """
    Manual search endpoint for agent-led queries.
    """
    try:
        return await cognee.search(request.query, limit=request.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/tools/stats/record")
async def record_tool_stats(event: ToolExecutionEvent):
    """
    Records a tool execution event for reliability tracking.
    """
    try:
        await rdbms.record_tool_execution(event)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/tools/stats/{agent_id}", response_model=ToolStatsResponse)
async def get_tool_stats(agent_id: str):
    """
    Retrieves the historical reliability statistics for tools bound to a specific agent.
    """
    try:
        stats = await rdbms.get_tool_stats(agent_id)
        return ToolStatsResponse(agent_id=agent_id, stats=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/sync", response_model=SyncResponse)
async def sync_sessions(request: SyncRequest):
    """
    Crawls OpenClaw's session logs and pulls them into Cognee.
    """
    import re
    if not re.match(r"^[a-zA-Z0-9_-]+$", request.agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent_id format")

    if not settings.sessions_dir:
        raise HTTPException(status_code=400, detail="sessions_dir not configured in Thalamus.")

    agent_sessions_path = Path(settings.sessions_dir) / request.agent_id / "sessions" / "sessions.json"
    if not agent_sessions_path.exists():
        raise HTTPException(status_code=404, detail=f"No sessions found for agent {request.agent_id}")

    try:
        with open(agent_sessions_path, "r") as f:
            sessions_data = json.load(f)

        messages_synced = 0
        sessions_scanned = 0
        
        # Determine which sessions to sync
        sessions_to_process = []
        if request.session_id:
            # Sync specific session
            for key, val in sessions_data.items():
                if val.get("sessionId") == request.session_id:
                    sessions_to_process.append(val)
                    break
        else:
            # Sync all sessions
            sessions_to_process = list(sessions_data.values())

        for session in sessions_to_process:
            jsonl_path = Path(session.get("sessionFile", ""))
            if not jsonl_path.exists():
                continue
            
            sessions_scanned += 1
            session_messages = []
            
            with open(jsonl_path, "r") as f:
                for line in f:
                    if not line.strip(): continue
                    msg = json.loads(line)
                    role = msg.get("role")
                    content = msg.get("content")
                    
                    if role in ["user", "assistant"] and content:
                        session_messages.append(MemoryMessage(
                            role=role,
                            content=str(content)
                        ))
            
            if session_messages:
                # Ingest into Cognee
                ingest_req = IngestRequest(
                    agent_id=request.agent_id,
                    conversation_id=session.get("sessionId"),
                    messages=session_messages
                )
                await cognee.add(ingest_req)
                messages_synced += len(session_messages)

        # Clear cache after bulk sync
        keys_to_clear = [k for k in context_cache.keys() if k[0] == request.agent_id]
        for k in keys_to_clear:
            del context_cache[k]

        # Notify via Webhook
        await broadcast_event("MEMORIES_SYNCED", request.agent_id, {
            "messages_synced": messages_synced,
            "sessions_scanned": sessions_scanned
        })

        return SyncResponse(
            status="success",
            messages_synced=messages_synced,
            new_facts_extracted=0, # Cognee handles extraction in background
            sessions_scanned=sessions_scanned
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)

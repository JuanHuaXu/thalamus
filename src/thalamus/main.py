from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from pathlib import Path
import json
import re
from cachetools import TTLCache
import httpx
import time
import asyncio
import aiosqlite
from contextlib import asynccontextmanager
from pydantic import BaseModel
import logging
from .api.schemas import IngestRequest, SearchRequest, ContextResponse, SearchResult, SyncRequest, SyncResponse, MemoryMessage, ToolExecutionEvent, ToolStatsResponse, SeedRequest, SeedResponse, SeedUndoRequest, DisputeRequest, BulkDisputeRequest, PurgeRequest, CompactRequest
from .providers.cognee import CogneeProvider
from .providers.relational import SQLiteRelationalProvider
from .providers.crawler import CrawlerProvider
from .core.config import settings
from .core.sanitizer import BinarySanitizer

logger = logging.getLogger(__name__)

# HTTP Bearer Auth
security = HTTPBearer(auto_error=False)

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if settings.api_key:
        if not credentials or credentials.credentials != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

ingestion_queue = asyncio.Queue(maxsize=settings.ingestion_queue_max_size)

async def process_ingestion_queue():
    print("[Thalamus Worker] Ingestion loop started.", flush=True)
    while True:
        task = await ingestion_queue.get()
        try:
            if task["type"] == "ingest":
                request = task["request"]
                for message in request.messages:
                    message.content = BinarySanitizer.sanitize_message(message.content)
                await cognee.add(request)
            elif task["type"] == "seed":
                request = task["request"]
                crawler = CrawlerProvider()
                for url in request.urls:
                    content = crawler.fetch_and_clean(url)
                    if content:
                        print(f"[Thalamus Worker] Extracted {len(content)} chars from {url}", flush=True)
                        dataset_name = f"doc_seed_{request.agent_id}"
                        await cognee.add_text(content, dataset_name=dataset_name)
                        await cognee.cognify(dataset_name=dataset_name)
                        print(f"[Thalamus Worker] Successfully seeded {url} to {dataset_name}", flush=True)
        except Exception as e:
            import traceback
            print(f"[Thalamus Worker] Error processing task: {str(e)}", flush=True)
            traceback.print_exc()
        finally:
            ingestion_queue.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await rdbms.initialize()
    worker = asyncio.create_task(process_ingestion_queue())
    yield
    worker.cancel()

app = FastAPI(title="Thalamus Middleware", version="0.1.0", dependencies=[Depends(verify_api_key)], lifespan=lifespan)

# Initialize providers
cognee = CogneeProvider()
rdbms = SQLiteRelationalProvider()

# In-memory caches
context_cache = TTLCache(maxsize=1000, ttl=settings.cache_ttl_seconds)
last_served_nodes = TTLCache(maxsize=100, ttl=600)  # agent_id -> set(node_ids)

async def broadcast_event(event_type: str, agent_id: str, payload: dict):
    # ... (rest of broadcast_event as before)
    pass

# --- API Schemas extension ---
# The SeedRequest and SeedResponse are now in api/schemas.py

@app.post("/v1/seed", status_code=202)
async def seed_knowledge(request: SeedRequest):
    """Authoritative ingestion from a list of documentation URLs."""
    await ingestion_queue.put({"type": "seed", "request": request})
    return {"status": "queued", "urls_submitted": len(request.urls)}

@app.get("/v1/seed/status")
async def seed_status():
    return {"status": "success", "queue_size": ingestion_queue.qsize()}

@app.post("/v1/seed/undo")
async def undo_seed(request: SeedUndoRequest):
    """
    Reverses the impact of a seeding operation by marking all associated facts as ARCHIVED.
    This fulfills the 'Scientific Method' by providing a clean way to prune test or 'brain rot' data.
    """
    await rdbms.bulk_dispute_agent_facts(request.agent_id)
    return {"status": "success", "agent_id": request.agent_id, "action": "ARCHIVED"}

@app.post("/v1/consolidate")
async def consolidate_knowledge(agent_id: str = "default"):
    """Triggers the synthesis of conflicting or redundant facts."""
    from .core.consolidator import ConsolidationEngine
    engine = ConsolidationEngine(cognee, rdbms)
    pruned = await engine.run_consolidation_pass(agent_id)
    return {"status": "success", "nodes_processed": pruned}

@app.post("/v1/ingest")
async def ingest_memories(request: IngestRequest):
    """Ingests messages and triggers the automated feedback loop (Scientific Method)."""
    try:
        # 1. Ingest to Cognee
        await ingestion_queue.put({"type": "ingest", "request": request})
        
        # 2. AUTOMATED FEEDBACK LOOP
        last_message = request.messages[-1].content.lower()
        is_failure = any(word in last_message for word in ["error", "failed", "didn't work", "cannot find", "not found", "broken"])
        is_success = any(word in last_message for word in ["success", "worked", "done", "fixed", "correct"])
        
        if is_failure or is_success:
            nodes_to_update = last_served_nodes.get(request.agent_id, set())
            if nodes_to_update:
                print(f"[Thalamus] Feedback for {len(nodes_to_update)} nodes: {'SUCCESS' if is_success else 'FAILURE'} (Verified: {request.is_verified})")
                for node_id in nodes_to_update:
                    await rdbms.record_fact_interaction(node_id, request.agent_id, success=is_success, is_verified=request.is_verified)
                last_served_nodes.pop(request.agent_id, None)

        # 3. Cache Invalidation
        keys_to_del = [k for k in context_cache.keys() if k.startswith(f"{request.agent_id}:")]
        for k in keys_to_del:
            del context_cache[k]
            
        await broadcast_event("MEMORIES_PUSHED", request.agent_id, {"messages_count": len(request.messages)})
        return {"status": "success"}
    except Exception as e:
        print(f"[Thalamus] Ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def normalize_query(q: str) -> str:
    """Canonicalize query to improve cache hit rate for minor variations."""
    # 1. Lowercase and strip punctuation
    q = re.sub(r'[^\w\s]', '', q.lower()).strip()
    # 2. Sort tokens to handle word-order variations (e.g. "berkshire profit" vs "profit berkshire")
    tokens = sorted(q.split())
    return " ".join(tokens)

@app.get("/v1/context", response_model=ContextResponse)
async def get_context(q: str, agent_id: str = "default"):
    """
    Orchestrates search across multiple providers and returns a pre-formatted context block with caching.
    """
    # --- Query Canonicalization (V1.5) ---
    norm_q = normalize_query(q)
    cache_key = f"{agent_id}:{norm_q}"
    
    if cache_key in context_cache:
        print(f"[Thalamus] L1 Cache hit for query: {q} (norm: {norm_q})")
        return context_cache[cache_key]

    # --- L2: Persistent Cache (SQLite) ---
    cached_data = await rdbms.get_cached_context(agent_id, norm_q)
    if cached_data:
        try:
            print(f"[Thalamus] L2 Cache hit for query: {q}")
            result = ContextResponse(**json.loads(cached_data))
            context_cache[cache_key] = result # Refill L1
            return result
        except Exception as e:
            print(f"[Thalamus] L2 Cache corruption detected: {e}")

    try:
        # --- STAGE 1 & 2: Parallel Broad Search ---
        # Query both chat history and documentation seeds simultaneously
        import time
        start_time = time.time()
        
        agent_dataset = f"agent_{agent_id}"
        seed_dataset = f"doc_seed_{agent_id}"
        
        # Parallelize the IO bound search calls with a hard timeout to prevent 60s+ hangs
        search_tasks = [
            asyncio.create_task(cognee.search(q, limit=2, dataset_name=agent_dataset, search_type="CHUNKS")),
            asyncio.create_task(cognee.search(q, limit=2, dataset_name=seed_dataset, search_type="CHUNKS"))
        ]
        
        done, pending = await asyncio.wait(
            search_tasks,
            timeout=25.0,
            return_when=asyncio.ALL_COMPLETED
        )
        
        all_results = []
        for task in done:
            try:
                all_results.extend(task.result())
            except Exception as e:
                print(f"[Thalamus] Search task failed: {e}", flush=True)
                
        # Cancel any hanging tasks
        for task in pending:
            task.cancel()
            print(f"[Thalamus] Search task timed out and was cancelled", flush=True)
        
        print(f"[Thalamus] Parallel search (done={len(done)}, pending={len(pending)}) completed in {time.time() - start_time:.4f}s", flush=True)
        
        # De-duplicate results by path to avoid edge-case pollution (especially in tests)
        seen_paths = set()
        unique_results = []
        for res in all_results:
            if res.path not in seen_paths:
                unique_results.append(res)
                seen_paths.add(res.path)
        all_results = unique_results

        # Track for feedback loop
        node_ids = {res.path for res in all_results}
        last_served_nodes[agent_id] = node_ids

        # Fetch reputations
        reputations = await rdbms.get_fact_reputations(agent_id)
        
        def sanitize(text: str) -> str:
            return re.sub(r'</?(relevant-memories|tool-reliability|latent-abstraction)>', '', text, flags=re.IGNORECASE)

        vetted_memories = [] # Surgical
        latent_memories = [] # Latent

        for mem in all_results:
            rep = reputations.get(mem.path)
            if rep:
                if rep["status"] == "DISPUTED":
                    continue
                vetted_memories.append(f"- [{mem.category or 'Memory'}] {sanitize(mem.snippet)}")
            else:
                latent_memories.append(f"- [Analogy ID: {mem.path}] {sanitize(mem.snippet)}")

        # --- STAGE 3: Mutation Fallback (Only if literally nothing) ---
        if not vetted_memories and not latent_memories:
            mutated_q = re.sub(r'\b(v?\d+\.\d+)\b', '', q).strip()
            if mutated_q and mutated_q != q:
                extra_results = await cognee.search(mutated_q, limit=3)
                for mem in extra_results:
                    latent_memories.append(f"- [Analogy ID: {mem.path}] {sanitize(mem.snippet)}")

        # Format blocks
        mem_block = f"<relevant-memories>\n" + "\n".join(vetted_memories) + "\n</relevant-memories>" if vetted_memories else ""
        latent_block = f"<latent-abstraction>\n" + "\n".join(latent_memories) + "\n</latent-abstraction>" if latent_memories else ""

        if not mem_block and not latent_block:
            mem_block = "<relevant-memories>\nNo high-confidence memories found.\n</relevant-memories>"

        # Tool Reputation
        tool_stats = await rdbms.get_tool_stats(agent_id)
        active_tool_stats = [ts for ts in tool_stats if ts.successes > 0 or ts.failures > 0]
        active_tool_stats.sort(key=lambda x: x.successes / (x.successes + x.failures) if (x.successes + x.failures) > 0 else 0, reverse=True)

        tool_block = ""
        if active_tool_stats:
            stats_list = "\n".join([
                f"- {ts.tool_name}: Reliability {int((ts.successes / (ts.successes + ts.failures)) * 100)}%"
                for ts in active_tool_stats
            ])
            tool_block = f"<tool-reliability>\n{stats_list}\n</tool-reliability>"
            
        combined_context = "\n\n".join(filter(None, [mem_block, latent_block, tool_block])).strip()
        
        response = ContextResponse(
            context=combined_context,
            metadata={
                "nodes_found": len(all_results),
                "nodes_vetted": len(vetted_memories),
                "latent_nodes": len(latent_memories),
                "lsa_triggered": len(latent_memories) > 0 and len(vetted_memories) == 0
            }
        )
        
        context_cache[cache_key] = response
        
        # --- L2: Populate Persistent Cache ---
        try:
            await rdbms.set_cached_context(agent_id, norm_q, response.model_dump_json(), ttl_seconds=settings.cache_ttl_seconds)
        except Exception as e:
            print(f"[Thalamus] L2 Cache population failed: {e}")

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/search", response_model=List[SearchResult])
async def manual_search(request: SearchRequest):
    """Deep search across the Cognee graph."""
    try:
        return await cognee.search(request.query, limit=request.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/context/dispute")
async def dispute_context_node(request: DisputeRequest):
    """Instantly marks a specific node as DISPUTED for an agent context."""
    try:
        async with aiosqlite.connect(rdbms.db_path) as db:
            now = int(time.time())
            await db.execute("""
                INSERT INTO fact_reputation (node_id, agent_id, failure_count, last_verified_at, status) 
                VALUES (?, ?, 10, ?, 'DISPUTED') 
                ON CONFLICT(node_id, agent_id) DO UPDATE SET 
                    failure_count = failure_count + 10, 
                    last_verified_at = ?,
                    status = 'DISPUTED'
            """, (request.node_id, request.agent_id, now, now))
            await db.commit()
            
        keys_to_del = [k for k in context_cache.keys() if k.startswith(f"{request.agent_id}:")]
        for k in keys_to_del:
            del context_cache[k]
            
        return {"status": "success", "action": "DISPUTED", "node_id": request.node_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/context/bulk-dispute")
async def bulk_dispute_context(request: BulkDisputeRequest):
    """Marks all nodes matching a query as DISPUTED to prune accidental ingestions."""
    try:
        # 1. Find nodes
        results = await cognee.search(request.query, limit=request.limit)
        node_ids = [res.path for res in results]
        
        if not node_ids:
            return {"status": "success", "nodes_hidden": 0, "message": "No matching nodes found."}

        # 2. Dispute them in SQLite
        await rdbms.bulk_dispute_nodes(request.agent_id, node_ids)
        
        # 3. Clear cache
        keys_to_del = [k for k in context_cache.keys() if k.startswith(f"{request.agent_id}:")]
        for k in keys_to_del:
            del context_cache[k]
            
        return {"status": "success", "nodes_hidden": len(node_ids), "query": request.query}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/v1/context/purge")
async def purge_context(request: PurgeRequest):
    """Hard-delete all memory data for an agent from Cognee and SQLite."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required to permanently delete all memory.")
    
    try:
        # 1. Delete Cognee Datasets (chat and seeds)
        deleted_cognee_count = await cognee.delete_agent_datasets(request.agent_id)
        
        # 2. Delete SQLite reputation entries
        await rdbms.purge_agent_reputation(request.agent_id)
        
        # 3. Clear Cache
        keys_to_del = [k for k in context_cache.keys() if k.startswith(f"{request.agent_id}:")]
        for k in keys_to_del:
            del context_cache[k]
            
        return {
            "status": "success", 
            "message": "Physical purge completed.",
            "agent_id": request.agent_id,
            "cognee_datasets_deleted": deleted_cognee_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/context/compact")
async def compact_context(request: CompactRequest):
    """Surgically removes facts with a specific status from SQLite for an agent."""
    try:
        # 1. Physical delete from SQLite
        await rdbms.compact_agent_reputation(request.agent_id, status=request.status_filter)
        
        # 2. Clear context cache (to ensure we re-evaluate reputation)
        keys_to_del = [k for k in context_cache.keys() if k.startswith(f"{request.agent_id}:")]
        for k in keys_to_del:
            del context_cache[k]
            
        return {
            "status": "success", 
            "message": f"Surgical compaction completed for status: {request.status_filter}",
            "agent_id": request.agent_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/tools/stats/record")
async def record_tool_stats(event: ToolExecutionEvent):
    """Telemetery for tool reliability."""
    try:
        await rdbms.record_tool_stats(event.agent_id, event.tool_name, event.status)
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

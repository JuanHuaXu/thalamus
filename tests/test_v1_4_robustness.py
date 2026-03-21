import pytest
import asyncio
import os
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from thalamus.main import app
from thalamus.core.config import settings
from thalamus.providers.relational import SQLiteRelationalProvider
from thalamus.api.schemas import ContextResponse

@pytest.fixture
async def test_db():
    db_path = "test_v1_4_robustness.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    settings.sessions_dir = "."
    provider = SQLiteRelationalProvider()
    provider.db_path = db_path
    await provider.initialize()
    yield provider
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
async def client(test_db):
    from thalamus import main
    mock_cognee = AsyncMock()
    # default search returns empty list
    mock_cognee.search = AsyncMock(return_value=[])
    
    with patch.object(main, 'rdbms', test_db), \
         patch.object(main, 'cognee', mock_cognee):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.mock_cognee = mock_cognee
            yield c

@pytest.mark.asyncio
async def test_l2_persistence_cycle(test_db):
    """Verify that L2 cache survives provider re-initialization (simulated restart)."""
    agent_id = "restart_agent"
    query = "persistent query"
    data = '{"context": "stored context", "metadata": {}}'
    
    # 1. Store data
    await test_db.set_cached_context(agent_id, query, data, ttl_seconds=100)
    
    # 2. Simulate "Restart" by creating a new provider on same DB
    new_provider = SQLiteRelationalProvider()
    new_provider.db_path = test_db.db_path
    await new_provider.initialize()
    
    # 3. Retrieve and verify
    retrieved = await new_provider.get_cached_context(agent_id, query)
    assert retrieved == data

@pytest.mark.asyncio
async def test_parallel_search_timeout_handling(client):
    """Verify that Thalamus handles a slow Cognee response within a short timeout."""
    # We will patch the timeout in main.py to be very small for the test
    # instead of patching asyncio.wait directly to avoid internal state issues.
    
    from thalamus import main
    async def slow_search(*args, **kwargs):
        await asyncio.sleep(2.0) # Sleep longer than our test timeout
        return []

    client.mock_cognee.search.side_effect = slow_search
    
    # We patch the 'timeout=25.0' in the actual call inside main.py if we can,
    # but since it's hardcoded, we'll keep the asyncio.wait patch but make it more robust.
    
    real_wait = asyncio.wait
    async def robust_fast_wait(tasks, timeout=25.0, return_when=asyncio.ALL_COMPLETED):
        # Force a tiny timeout for the test
        return await real_wait(tasks, timeout=0.1, return_when=return_when)

    with patch("asyncio.wait", side_effect=robust_fast_wait):
        resp = await client.get("/v1/context?q=slow+query&agent_id=test_agent")
        assert resp.status_code == 200
        data = resp.json()
        assert "No high-confidence memories found" in data["context"]
        assert data["metadata"]["nodes_found"] == 0

@pytest.mark.asyncio
async def test_l1_l2_cache_refill(client, test_db):
    """Verify that L2 hit refills the L1 in-memory cache."""
    from thalamus import main
    agent_id = "refill_agent"
    query = "refill query"
    # Populate L2 only
    res_obj = ContextResponse(context="L2 data", metadata={"nodes_found": 1})
    await test_db.set_cached_context(agent_id, query, res_obj.model_dump_json(), ttl_seconds=100)
    
    # Ensure L1 is empty
    cache_key = f"{agent_id}:{query}"
    if cache_key in main.context_cache:
        del main.context_cache[cache_key]
        
    # Trigger request
    resp = await client.get(f"/v1/context?q={query}&agent_id={agent_id}")
    assert resp.status_code == 200
    assert "L2 data" in resp.json()["context"]
    
    # Verify L1 is now filled
    assert cache_key in main.context_cache
    assert main.context_cache[cache_key].context == "L2 data"

@pytest.mark.asyncio
async def test_initialization_robustness(test_db):
    """Verify initialization doesn't fail on second call (typical of service restart)."""
    # Second initialization should be idempotent
    await test_db.initialize()
    # Even if we "corrupt" the schema by deleting it while open (simulated), 
    # a fresh init should handle what it can
    pass 

import pytest
import asyncio
import os
import time
import aiosqlite
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from thalamus.main import app
from thalamus.providers.relational import SQLiteRelationalProvider
from thalamus.core.config import settings

# Mock Cognee to avoid installation issues on Python 3.14
from unittest.mock import AsyncMock
@pytest.fixture(autouse=True)
def mock_cognee():
    with patch("thalamus.main.cognee") as mock:
        mock.search = AsyncMock(return_value=[])
        mock.add = AsyncMock(return_value=None)
        mock.add_text = AsyncMock(return_value=None)
        mock.cognify = AsyncMock(return_value=None)
        yield mock

@pytest.fixture
async def test_db():
    db_path = "test_thalamus_rdbms.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    settings.sessions_dir = "."
    provider = SQLiteRelationalProvider()
    provider.db_path = db_path
    await provider.initialize()
    # v1.4 robustness: ensure cache is clean
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM persistent_context_cache")
        await db.commit()
    return provider

@pytest.fixture
async def client(test_db):
    # Patch the global rdbms in main.py to use our test DB
    with patch("thalamus.main.rdbms", test_db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

@pytest.mark.asyncio
async def test_fact_reputation_dispute_api(client, test_db):
    agent_id = "test_agent"
    node_id = "node_123"
    
    # 1. Mock Cognee to return a specific node
    from thalamus.api.schemas import SearchResult
    mock_res = SearchResult(path=node_id, snippet="The sky is green.", category="Fact", score=0.9)
    
    with patch("thalamus.main.cognee.search", new_callable=MagicMock) as mock_search:
        mock_search.side_effect = lambda *args, **kwargs: asyncio.sleep(0, [mock_res])
        # Wait, better to use AsyncMock directly if available or just return a coroutine
        async def async_ret(*args, **kwargs): return [mock_res]
        mock_search.side_effect = async_ret
        # Call context (this tracks the node in last_served_nodes)
        resp = await client.get(f"/v1/context?q=test&agent_id={agent_id}")
        if resp.status_code != 200:
            print(f"DEBUG: Response Error Detail: {resp.json()}")
        assert resp.status_code == 200
        assert "The sky is green." in resp.json()["context"]

    # 2. Ingest a FAILURE message
    await client.post("/v1/ingest", json={
        "agent_id": agent_id,
        "conversation_id": "conv_1",
        "messages": [{"role": "assistant", "content": "That was an error and failed."}]
    })

    # 3. Check reputation
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps[node_id]["failure"] == 1

@pytest.mark.asyncio
async def test_disputed_fact_filtering(client, test_db):
    agent_id = "test_agent"
    node_id = "rot_node"
    
    # 1. Manually mark a node as DISPUTED in the DB
    # We'll use the record_fact_interaction repeatedly or just mock the DB result
    await test_db.record_fact_interaction(node_id, agent_id, success=False)
    await test_db.record_fact_interaction(node_id, agent_id, success=False)
    await test_db.record_fact_interaction(node_id, agent_id, success=False)
    
    # 2. Mock Cognee to return this "rot" node
    from thalamus.api.schemas import SearchResult
    mock_res = SearchResult(path=node_id, snippet="This is brain rot.", category="Fact", score=0.9)
    
    with patch("thalamus.main.cognee.search", AsyncMock(return_value=[mock_res])):
        resp = await client.get(f"/v1/context?q=test&agent_id={agent_id}")
        assert resp.status_code == 200
        # The node should be FILTERED OUT
        assert "This is brain rot." not in resp.json()["context"]
        assert "No high-confidence memories found." in resp.json()["context"]

@pytest.mark.asyncio
async def test_crawler_extraction():
    from thalamus.providers.crawler import CrawlerProvider
    # Mock trafilatura.fetch_url and extract with realistically long content
    long_content = "This is a realistically long piece of documentation content that should pass the quality threshold. " * 5
    with patch("trafilatura.fetch_url", return_value="<html><body>" + long_content + "</body></html>"):
        with patch("trafilatura.extract", return_value=long_content):
            content = CrawlerProvider.fetch_and_clean("https://example.com")
            assert content == long_content

@pytest.mark.asyncio
async def test_crawler_multi_format_routing():
    from thalamus.providers.crawler import CrawlerProvider
    
    # 1. Test Raw Code Routing (e.g. .js file)
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "text/javascript"}
        mock_response.text = "function hello() { console.log('world'); }"
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        content = CrawlerProvider.fetch_and_clean("https://example.com/script.js")
        assert "function hello()" in content
        assert "console.log" in content

    # 2. Test PDF Routing (Mocked)
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"%PDF-1.4..."
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        with patch("thalamus.providers.crawler.CrawlerProvider._extract_pdf", return_value="PDF Text"):
            content = CrawlerProvider.fetch_and_clean("https://example.com/doc.pdf")
            assert content == "PDF Text"

@pytest.mark.asyncio
async def test_crawler_brain_rot_detection():
    from thalamus.providers.crawler import CrawlerProvider
    # 1. Test too short
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "Short"
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        with patch("trafilatura.extract", return_value="Short"):
            content = CrawlerProvider.fetch_and_clean("https://tiny.com")
            assert content is None

    # 2. Test block signature
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "Please complete the CAPTCHA."
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        with patch("trafilatura.extract", return_value="Access Denied. CAPTCHA required."):
            content = CrawlerProvider.fetch_and_clean("https://blocked.com")
            assert content is None

@pytest.mark.asyncio
async def test_dynamic_threshold_decay(test_db):
    agent_id = "test_dynamic_decay_agent"
    node_id = "node_dynamic"

    # Initial state: ACTIVE
    await test_db.record_fact_interaction(node_id, agent_id, success=True, is_verified=True)
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps[node_id]["status"] == "ACTIVE"
    assert reps[node_id]["dynamic_threshold"] == settings.initial_dynamic_threshold

    # Failures should increase dynamic_threshold
    for i in range(3):
        await test_db.record_fact_interaction(node_id, agent_id, success=False, is_verified=True)
        reps = await test_db.get_fact_reputations(agent_id)
        assert reps[node_id]["status"] == "ACTIVE" # Still active
        assert reps[node_id]["dynamic_threshold"] > settings.initial_dynamic_threshold

    # Successes should decrease dynamic_threshold
    initial_threshold_after_failures = reps[node_id]["dynamic_threshold"]
    for i in range(2):
        await test_db.record_fact_interaction(node_id, agent_id, success=True, is_verified=True)
        reps = await test_db.get_fact_reputations(agent_id)
        assert reps[node_id]["status"] == "ACTIVE"
        assert reps[node_id]["dynamic_threshold"] < initial_threshold_after_failures

    # Test dispute based on dynamic threshold
    # Reset and make it fail enough times to exceed the dynamic threshold
    await test_db.record_fact_interaction(node_id, agent_id, success=True, is_verified=True) # Reset to initial threshold
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps[node_id]["dynamic_threshold"] == settings.initial_dynamic_threshold

    # Fail enough times to exceed the initial dynamic threshold
    for i in range(settings.initial_dynamic_threshold):
        await test_db.record_fact_interaction(node_id, agent_id, success=False, is_verified=True)
        reps = await test_db.get_fact_reputations(agent_id)
        if i < settings.initial_dynamic_threshold - 1:
            assert reps[node_id]["status"] == "ACTIVE"
        else:
            assert reps[node_id]["status"] == "DISPUTED"

@pytest.mark.asyncio
async def test_is_verified_fact_decay(test_db):
    agent_id = "test_decay_agent"
    
    # Node 1: Unverified. Should dispute after settings.unverified_dispute_threshold failures.
    node_unverified = "node_unv"
    for i in range(settings.unverified_dispute_threshold - 1):
        await test_db.record_fact_interaction(node_unverified, agent_id, success=False, is_verified=False)
        reps = await test_db.get_fact_reputations(agent_id)
        assert reps[node_unverified]["status"] == "ACTIVE"
    
    await test_db.record_fact_interaction(node_unverified, agent_id, success=False, is_verified=False)
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps[node_unverified]["status"] == "DISPUTED"
    
    # Node 2: Verified. Should still be ACTIVE after threshold-1 failures.
    node_verified = "node_ver"
    # First, log a success to set is_verified = 1
    await test_db.record_fact_interaction(node_verified, agent_id, success=True, is_verified=True)
    
    for _ in range(settings.verified_dispute_threshold - 1):
        await test_db.record_fact_interaction(node_verified, agent_id, success=False, is_verified=True)
        reps = await test_db.get_fact_reputations(agent_id)
        assert reps[node_verified]["status"] == "ACTIVE"
        
    await test_db.record_fact_interaction(node_verified, agent_id, success=False, is_verified=True)
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps[node_verified]["status"] == "DISPUTED"

@pytest.mark.asyncio
async def test_async_ingest_queue(client):
    payload = {
        "agent_id": "test_agent_async",
        "messages": [
            {"role": "user", "content": "Is this fast?"},
            {"role": "assistant", "content": "Success."}
        ],
        "is_verified": True
    }
    response = await client.post("/v1/ingest", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@pytest.mark.asyncio
async def test_reject_analogy_endpoint(client, test_db):
    payload = {
        "agent_id": "test_agent_async",
        "node_id": "fake_analogy_id_123"
    }
    response = await client.post("/v1/context/dispute", json=payload)
    assert response.status_code == 200
    assert response.json()["action"] == "DISPUTED"
    
    reps = await test_db.get_fact_reputations("test_agent_async")
    assert reps["fake_analogy_id_123"]["status"] == "DISPUTED"

@pytest.mark.asyncio
async def test_consolidation_engine(test_db):
    from thalamus.core.consolidator import ConsolidationEngine
    from unittest.mock import AsyncMock
    mock_cognee = AsyncMock()
    engine = ConsolidationEngine(mock_cognee, test_db)
    
    agent_id = "test_agent_consolidation"
    
    # Need settings.consolidation_cluster_size active nodes to trigger consolidation
    for i in range(settings.consolidation_cluster_size):
        await test_db.record_fact_interaction(f"node_{i}", agent_id, success=True, is_verified=True)
        
    pruned = await engine.run_consolidation_pass(agent_id)
    assert pruned == settings.consolidation_cluster_size
    
    # Check that they are tombstoned
    reps = await test_db.get_fact_reputations(agent_id)
    for i in range(settings.consolidation_cluster_size):
        assert reps[f"node_{i}"]["status"] == "CONSOLIDATED"
        
    # Check that a new wisdom node was created
    wisdom_nodes = [node_id for node_id, rep in reps.items() if node_id.startswith("wisdom_")]
    assert len(wisdom_nodes) == 1
    assert reps[wisdom_nodes[0]]["status"] == "ACTIVE"

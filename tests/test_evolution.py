import pytest
import asyncio
import os
import time
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

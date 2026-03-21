import pytest
import asyncio
import os
import io
import time
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from thalamus.main import app
from thalamus.core.config import settings
from thalamus.providers.relational import SQLiteRelationalProvider
from thalamus.core.sanitizer import BinarySanitizer

@pytest.fixture
async def test_db():
    db_path = "test_v1_thalamus.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    settings.sessions_dir = "."
    provider = SQLiteRelationalProvider()
    provider.db_path = db_path
    await provider.initialize()
    return provider

@pytest.fixture
async def client(test_db):
    from thalamus import main
    mock_cognee = AsyncMock()
    mock_cognee.search = AsyncMock(return_value=[])
    mock_cognee.add = AsyncMock()
    mock_cognee.delete_agent_datasets = AsyncMock(return_value=1)
    
    with patch.object(main, 'rdbms', test_db), \
         patch.object(main, 'cognee', mock_cognee):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.mock_cognee = mock_cognee
            yield c

@pytest.mark.asyncio
async def test_binary_sanitizer_pdf():
    import base64
    pdf_content_b64 = base64.b64encode(b"%PDF-1.4 mock content").decode()
    with patch("pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted PDF Text"
        mock_reader.return_value.pages = [mock_page]
        
        result = BinarySanitizer._process_binary_block(pdf_content_b64)
        assert "Extracted PDF Text" in result

@pytest.mark.asyncio
async def test_binary_sanitizer_image():
    import base64
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    png_content_b64 = base64.b64encode(png_content).decode()
    result = BinarySanitizer._process_binary_block(png_content_b64)
    assert "[IMAGE: PNG, 1x1]" in result

@pytest.mark.asyncio
async def test_binary_sanitizer_integration():
    import base64
    png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR42mP8/5+hPQAHggJ/flfzzwAAAABJRU5ErkJggg=="
    content = f"Check this: data:image/png;base64,{png_base64}"
    sanitized = BinarySanitizer.sanitize_message(content)
    assert "[IMAGE: PNG, 1x1]" in sanitized
    assert png_base64 not in sanitized

@pytest.mark.asyncio
async def test_bulk_dispute_endpoint(client, test_db):
    from thalamus.api.schemas import SearchResult
    agent_id = "test_bulk_agent"
    client.mock_cognee.search.return_value = [
        SearchResult(path="node_1", snippet="Bad fact 1", category="Fact", score=0.9),
        SearchResult(path="node_2", snippet="Bad fact 2", category="Fact", score=0.8)
    ]
    resp = await client.post("/v1/context/bulk-dispute", json={
        "agent_id": agent_id,
        "query": "bad",
        "limit": 5
    })
    assert resp.status_code == 200
    assert resp.json()["nodes_hidden"] == 2
    reps = await test_db.get_fact_reputations(agent_id)
    assert reps["node_1"]["status"] == "DISPUTED"
    assert reps["node_2"]["status"] == "DISPUTED"

@pytest.mark.asyncio
async def test_compact_endpoint(client, test_db):
    agent_id = "test_compact_agent"
    await test_db.record_fact_interaction("node_to_keep", agent_id, success=True)
    await test_db.record_fact_interaction("node_to_purge", agent_id, success=False)
    import aiosqlite
    async with aiosqlite.connect(test_db.db_path) as db:
        await db.execute("UPDATE fact_reputation SET status = 'DISPUTED' WHERE node_id = 'node_to_purge'")
        await db.commit()
    resp = await client.post("/v1/context/compact", json={
        "agent_id": agent_id,
        "status_filter": "DISPUTED"
    })
    assert resp.status_code == 200
    reps = await test_db.get_fact_reputations(agent_id)
    assert "node_to_purge" not in reps

@pytest.mark.asyncio
async def test_purge_endpoint(client, test_db):
    agent_id = "test_purge_agent"
    await test_db.record_fact_interaction("some_node", agent_id, success=True)
    resp = await client.request("DELETE", "/v1/context/purge", json={
        "agent_id": agent_id,
        "confirm": True
    })
    assert resp.status_code == 200
    reps = await test_db.get_fact_reputations(agent_id)
    assert len(reps) == 0

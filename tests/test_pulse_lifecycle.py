import pytest
import asyncio
import os
import time
import aiosqlite
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from thalamus.main import app
from thalamus.providers.relational import SQLiteRelationalProvider
from thalamus.core.config import settings

# Mock Cognee to avoid installation issues on Python 3.14
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
    db_path = "test_pulse_lifecycle.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    settings.sessions_dir = "."
    provider = SQLiteRelationalProvider()
    provider.db_path = db_path
    await provider.initialize()
    return provider

@pytest.fixture
async def client(test_db):
    with patch("thalamus.main.rdbms", test_db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_evict_stale_goals(test_db):
    """Insert 5 goals with created_at set to >24h ago, call evict_stale_goals, assert 0 remaining."""
    agent_id = "test_evict"
    old_timestamp = int(time.time()) - 90000  # ~25 hours ago

    for i in range(5):
        goal = {
            "id": f"old_goal_{i}",
            "description": f"Old goal {i}",
            "status": "pending",
            "priority": 5,
        }
        await test_db.upsert_pulse_goal(goal, agent_id)

    # Manually backdate created_at
    async with aiosqlite.connect(test_db.db_path) as db:
        await db.execute(
            "UPDATE pulse_goals SET created_at = ? WHERE agent_id = ?",
            (old_timestamp, agent_id)
        )
        await db.commit()

    evicted = await test_db.evict_stale_goals(agent_id, max_age_seconds=86400)
    assert evicted == 5

    remaining = await test_db.get_pulse_goals(agent_id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_deduplicate_goals(test_db):
    """Insert 3 goals with identical descriptions but different IDs. Only the newest should survive."""
    agent_id = "test_dedup"

    for i in range(3):
        goal = {
            "id": f"dup_goal_{i}",
            "description": "List files in root directory",
            "status": "pending",
            "priority": 5,
        }
        await test_db.upsert_pulse_goal(goal, agent_id)
        # Stagger created_at so each has a unique timestamp
        async with aiosqlite.connect(test_db.db_path) as db:
            await db.execute(
                "UPDATE pulse_goals SET created_at = ? WHERE id = ?",
                (int(time.time()) - (3 - i) * 100, f"dup_goal_{i}")
            )
            await db.commit()

    deduped = await test_db.deduplicate_goals(agent_id)
    assert deduped == 2

    remaining = await test_db.get_pulse_goals(agent_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == "dup_goal_2"  # newest


@pytest.mark.asyncio
async def test_compact_completed_goals(test_db):
    """Insert completed goals with old timestamps, call compact, assert they are removed."""
    agent_id = "test_compact"
    old_timestamp = int(time.time()) - 700000  # ~8 days ago

    for i in range(3):
        goal = {
            "id": f"done_goal_{i}",
            "description": f"Completed goal {i}",
            "status": "completed",
            "priority": 5,
        }
        await test_db.upsert_pulse_goal(goal, agent_id)

    # Backdate
    async with aiosqlite.connect(test_db.db_path) as db:
        await db.execute(
            "UPDATE pulse_goals SET created_at = ? WHERE agent_id = ?",
            (old_timestamp, agent_id)
        )
        await db.commit()

    compacted = await test_db.compact_completed_goals(agent_id, max_age_seconds=604800)
    assert compacted == 3

    remaining = await test_db.get_pulse_goals(agent_id)
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_evict_api_endpoint(client, test_db):
    """Call DELETE /v1/pulse/goals/evict via the test HTTP client. Assert response contains eviction counts."""
    agent_id = "test_api_evict"
    old_timestamp = int(time.time()) - 90000

    # Insert old pending goals
    for i in range(3):
        goal = {
            "id": f"api_old_{i}",
            "description": f"API old goal {i}",
            "status": "pending",
            "priority": 5,
        }
        await test_db.upsert_pulse_goal(goal, agent_id)

    # Backdate
    async with aiosqlite.connect(test_db.db_path) as db:
        await db.execute(
            "UPDATE pulse_goals SET created_at = ? WHERE agent_id = ?",
            (old_timestamp, agent_id)
        )
        await db.commit()

    resp = await client.request("DELETE", f"/v1/pulse/goals/evict?agent_id={agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["evicted"] == 3
    assert data["total_removed"] >= 3


@pytest.mark.asyncio
async def test_dedup_preserves_running(test_db):
    """Insert a running goal with same description as a pending one. The running goal must NOT be evicted."""
    agent_id = "test_preserve_running"

    # Insert a running goal
    await test_db.upsert_pulse_goal({
        "id": "running_goal_1",
        "description": "List files in root directory",
        "status": "running",
        "priority": 10,
    }, agent_id)

    # Insert a pending duplicate
    await test_db.upsert_pulse_goal({
        "id": "pending_goal_1",
        "description": "List files in root directory",
        "status": "pending",
        "priority": 5,
    }, agent_id)

    deduped = await test_db.deduplicate_goals(agent_id)
    # The dedup should NOT touch the running goal
    remaining = await test_db.get_pulse_goals(agent_id)
    running = [g for g in remaining if g["status"] == "running"]
    assert len(running) == 1
    assert running[0]["id"] == "running_goal_1"


# --- Drive State Tests ---

@pytest.mark.asyncio
async def test_drive_state_default(test_db):
    """Call get_drive_state on a fresh agent. Assert returns defaults (1.0, 0.3, 0.3)."""
    agent_id = "test_drive_default"
    state = await test_db.get_drive_state(agent_id)
    assert state["energy"] == 1.0
    assert state["curiosity"] == 0.3
    assert state["sociability"] == 0.3
    assert "lastUpdate" in state


@pytest.mark.asyncio
async def test_drive_state_update(test_db):
    """Call update_drive_state, then get_drive_state. Assert persisted values match."""
    agent_id = "test_drive_update"
    await test_db.update_drive_state(agent_id, 0.5, 0.8, 0.9)
    state = await test_db.get_drive_state(agent_id)
    assert state["energy"] == 0.5
    assert state["curiosity"] == 0.8
    assert state["sociability"] == 0.9


@pytest.mark.asyncio
async def test_drive_state_api(client, test_db):
    """Call PUT /v1/pulse/drives, then GET /v1/pulse/drives. Assert round-trip."""
    agent_id = "test_api_drives"
    
    # 1. Update via PUT
    put_resp = await client.request("PUT", f"/v1/pulse/drives?agent_id={agent_id}", json={
        "energy": 0.2,
        "curiosity": 0.7,
        "sociability": 0.1
    })
    assert put_resp.status_code == 200
    
    # 2. Fetch via GET
    get_resp = await client.request("GET", f"/v1/pulse/drives?agent_id={agent_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["energy"] == 0.2
    assert data["curiosity"] == 0.7
    assert data["sociability"] == 0.1

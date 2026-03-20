import aiosqlite
import os
import time
from typing import List, Optional
from pydantic import BaseModel
from ..core.config import settings

class ToolStat(BaseModel):
    tool_name: str
    successes: int = 0
    failures: int = 0
    blocks: int = 0

class SQLiteRelationalProvider:
    def __init__(self):
        self.db_path = "thalamus_rdbms.db" if not settings.sessions_dir else f"{settings.sessions_dir}/thalamus_rdbms.db"

    async def initialize(self):
        """Initializes the database schema asynchronously."""
        async with aiosqlite.connect(self.db_path) as db:
            # Tool Stats
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tool_stats (
                    agent_id TEXT,
                    tool_name TEXT,
                    successes INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0,
                    blocks INTEGER DEFAULT 0,
                    PRIMARY KEY (agent_id, tool_name)
                )
            """)
            
            # Fact Reputation (The "Scientific Method" Layer)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS fact_reputation (
                    node_id TEXT,
                    agent_id TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_verified_at INTEGER,
                    status TEXT DEFAULT 'ACTIVE',
                    PRIMARY KEY (node_id, agent_id)
                )
            """)
            
            # Consolidation Log
            await db.execute("""
                CREATE TABLE IF NOT EXISTS consolidation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    timestamp INTEGER,
                    nodes_merged_count INTEGER,
                    new_node_id TEXT,
                    summary TEXT
                )
            """)
            
            await db.commit()

    async def record_tool_stats(self, agent_id: str, tool_name: str, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            if status == "success":
                await db.execute("""
                    INSERT INTO tool_stats (agent_id, tool_name, successes) 
                    VALUES (?, ?, 1) ON CONFLICT(agent_id, tool_name) 
                    DO UPDATE SET successes = successes + 1
                """, (agent_id, tool_name))
            elif status == "failed":
                await db.execute("""
                    INSERT INTO tool_stats (agent_id, tool_name, failures) 
                    VALUES (?, ?, 1) ON CONFLICT(agent_id, tool_name) 
                    DO UPDATE SET failures = failures + 1
                """, (agent_id, tool_name))
            elif status == "blocked":
                await db.execute("""
                    INSERT INTO tool_stats (agent_id, tool_name, blocks) 
                    VALUES (?, ?, 1) ON CONFLICT(agent_id, tool_name) 
                    DO UPDATE SET blocks = blocks + 1
                """, (agent_id, tool_name))
            await db.commit()

    async def get_tool_stats(self, agent_id: str) -> List[ToolStat]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT tool_name, successes, failures, blocks FROM tool_stats WHERE agent_id = ?", (agent_id,)) as cursor:
                rows = await cursor.fetchall()
                return [ToolStat(tool_name=row[0], successes=row[1], failures=row[2], blocks=row[3]) for row in rows]

    # --- Evolutionary Knowledge Methods ---

    async def record_fact_interaction(self, node_id: str, agent_id: str, success: bool):
        """Weights the reputation of a specific fact node based on whether its use led to success."""
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            if success:
                await db.execute("""
                    INSERT INTO fact_reputation (node_id, agent_id, success_count, last_verified_at) 
                    VALUES (?, ?, 1, ?) 
                    ON CONFLICT(node_id, agent_id) DO UPDATE SET success_count = success_count + 1, last_verified_at = ?
                """, (node_id, agent_id, now, now))
            else:
                await db.execute("""
                    INSERT INTO fact_reputation (node_id, agent_id, failure_count, last_verified_at) 
                    VALUES (?, ?, 1, ?) 
                    ON CONFLICT(node_id, agent_id) DO UPDATE SET 
                        failure_count = failure_count + 1, 
                        last_verified_at = ?,
                        status = CASE WHEN failure_count + 1 >= 3 THEN 'DISPUTED' ELSE status END
                """, (node_id, agent_id, now, now))
            await db.commit()

    async def get_fact_reputations(self, agent_id: str) -> dict:
        """Returns a mapping of node_id to reputation metadata."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT node_id, success_count, failure_count, status FROM fact_reputation WHERE agent_id = ?", (agent_id,)) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: {"success": row[1], "failure": row[2], "status": row[3]} for row in rows}

    async def search(self, query: str, limit: int) -> List[SearchResult]:
        return []

    async def add(self, request: IngestRequest) -> None:
        pass

    async def bulk_dispute_agent_facts(self, agent_id: str):
        """Marks all facts for an agent as ARCHIVED, effectively 'undoing' their influence."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE fact_reputation SET status = 'ARCHIVED' WHERE agent_id = ?",
                (agent_id,)
            )
            await db.commit()

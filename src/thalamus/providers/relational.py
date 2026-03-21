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
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            
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
                    dynamic_threshold INTEGER DEFAULT 5,
                    last_verified_at INTEGER,
                    status TEXT DEFAULT 'ACTIVE',
                    is_verified INTEGER DEFAULT 0,
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
            
            # Column Migration
            cursor = await db.execute("PRAGMA table_info(fact_reputation)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "dynamic_threshold" not in columns:
                await db.execute("ALTER TABLE fact_reputation ADD COLUMN dynamic_threshold INTEGER DEFAULT 5")
            
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

    async def record_fact_interaction(self, node_id: str, agent_id: str, success: bool, is_verified: bool = False):
        """Record a fact hit or miss and update its reputation."""
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            if success:
                # On success, we reset failures and decay the dynamic threshold back towards initial
                await db.execute("""
                    INSERT INTO fact_reputation (node_id, agent_id, success_count, failure_count, dynamic_threshold, last_verified_at, is_verified)
                    VALUES (?, ?, 1, 0, ?, ?, ?)
                    ON CONFLICT(node_id, agent_id) DO UPDATE SET 
                        success_count = success_count + 1,
                        failure_count = 0,
                        dynamic_threshold = MAX(?, dynamic_threshold - 1),
                        last_verified_at = ?,
                        is_verified = CASE WHEN ? = 1 THEN 1 ELSE is_verified END
                """, (node_id, agent_id, settings.initial_dynamic_threshold, now, 1 if is_verified else 0, settings.initial_dynamic_threshold, now, 1 if is_verified else 0))
            else:
                # On failure, we increment failure count and increase the dynamic threshold (penalty)
                await db.execute("""
                    INSERT INTO fact_reputation (node_id, agent_id, success_count, failure_count, dynamic_threshold, last_verified_at, is_verified)
                    VALUES (?, ?, 0, 1, ?, ?, ?)
                    ON CONFLICT(node_id, agent_id) DO UPDATE SET 
                        failure_count = failure_count + 1, 
                        dynamic_threshold = dynamic_threshold + 1,
                        last_verified_at = ?,
                        status = CASE WHEN failure_count + 1 >= (CASE WHEN fact_reputation.is_verified = 1 THEN ? ELSE ? END) 
                                     OR failure_count + 1 >= dynamic_threshold THEN 'DISPUTED' ELSE status END
                """, (node_id, agent_id, settings.initial_dynamic_threshold + 1, now, 1 if is_verified else 0, now, settings.verified_dispute_threshold, settings.unverified_dispute_threshold))
            await db.commit()

    async def get_fact_reputations(self, agent_id: str) -> dict:
        """Fetch reputation scores for all facts associated with an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM fact_reputation WHERE agent_id = ?", (agent_id,))
            rows = await cursor.fetchall()
            return {row["node_id"]: {
                "success": row["success_count"],
                "failure": row["failure_count"],
                "dynamic_threshold": row["dynamic_threshold"],
                "status": row["status"],
                "is_verified": bool(row["is_verified"])
            } for row in rows}

    async def search(self, query: str, limit: int) -> List[SearchResult]:
        return []

    async def add(self, request: IngestRequest) -> None:
        pass

    async def bulk_dispute_nodes(self, agent_id: str, node_ids: List[str]):
        """Instantly marks a specific list of nodes as DISPUTED for an agent context."""
        if not node_ids:
            return
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            for node_id in node_ids:
                await db.execute("""
                    INSERT INTO fact_reputation (node_id, agent_id, failure_count, last_verified_at, status) 
                    VALUES (?, ?, 10, ?, 'DISPUTED') 
                    ON CONFLICT(node_id, agent_id) DO UPDATE SET 
                        failure_count = failure_count + 10, 
                        last_verified_at = ?,
                        status = 'DISPUTED'
                """, (node_id, agent_id, now, now))
            await db.commit()

    async def bulk_dispute_agent_facts(self, agent_id: str):
        """Marks all facts for an agent as ARCHIVED, effectively 'undoing' their influence."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE fact_reputation SET status = 'ARCHIVED' WHERE agent_id = ?",
                (agent_id,)
            )
            await db.commit()

    async def purge_agent_reputation(self, agent_id: str):
        """Physically deletes all reputation entries for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM fact_reputation WHERE agent_id = ?",
                (agent_id,)
            )
            await db.commit()

    async def compact_agent_reputation(self, agent_id: str, status: str = "DISPUTED"):
        """Surgically deletes only facts with a specific status (e.g. DISPUTED)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM fact_reputation WHERE agent_id = ? AND status = ?",
                (agent_id, status)
            )
            await db.commit()

import aiosqlite
import json
import os
import time
from typing import List, Optional
from pydantic import BaseModel
from ..core.config import settings
from ..api.schemas import Abstraction

class ToolStat(BaseModel):
    tool_name: str
    successes: int = 0
    failures: int = 0
    blocks: int = 0

class SQLiteRelationalProvider:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or ("thalamus_rdbms.db" if not settings.sessions_dir else f"{settings.sessions_dir}/thalamus_rdbms.db")

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
            
            # Persistent Context Cache (V1.3 Performance)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS persistent_context_cache (
                    cache_key TEXT PRIMARY KEY,
                    agent_id TEXT,
                    query TEXT,
                    context_data TEXT,
                    expiry_timestamp INTEGER
                )
            """)

            # V2.0 Seed Job Tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS seed_jobs (
                    job_id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    status TEXT,
                    urls TEXT,
                    results TEXT,
                    created_at INTEGER,
                    updated_at INTEGER
                )
            """)

            # Phase 2: LSA Abstractions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS abstractions (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    name TEXT,
                    description TEXT,
                    abstraction_type TEXT,
                    source_refs TEXT, -- JSON list
                    support_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.5,
                    invariants TEXT, -- JSON list
                    variables TEXT, -- JSON dict
                    conditions TEXT, -- JSON list
                    effects TEXT, -- JSON list
                    temporal_scope TEXT, -- JSON dict
                    succession_links TEXT, -- JSON dict
                    supersedes TEXT,
                    superseded_by TEXT,
                    contention_group_id TEXT,
                    decay_score REAL DEFAULT 1.0,
                    created_at INTEGER,
                    last_updated_at INTEGER
                )
            """)
            
            # Column Migration
            cursor = await db.execute("PRAGMA table_info(fact_reputation)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "dynamic_threshold" not in columns:
                await db.execute("ALTER TABLE fact_reputation ADD COLUMN dynamic_threshold INTEGER DEFAULT 5")
            if "abstraction_id" not in columns:
                await db.execute("ALTER TABLE fact_reputation ADD COLUMN abstraction_id TEXT")
            
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

    async def upsert_fact_reputation(self, node_id: str, agent_id: str, success_count: int = 1, last_verified_at: Optional[int] = None, status: str = "ACTIVE", is_verified: bool = False, abstraction_id: Optional[str] = None):
        """Directly upserts a fact reputation record."""
        now = last_verified_at or int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO fact_reputation (node_id, agent_id, success_count, last_verified_at, status, is_verified, abstraction_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id, agent_id) DO UPDATE SET
                    success_count = excluded.success_count,
                    last_verified_at = excluded.last_verified_at,
                    status = excluded.status,
                    is_verified = excluded.is_verified,
                    abstraction_id = excluded.abstraction_id
            """, (node_id, agent_id, success_count, now, status, 1 if is_verified else 0, abstraction_id))
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

    async def get_cached_context(self, agent_id: str, query: str) -> Optional[str]:
        """Fetch cached context result if it exists and hasn't expired."""
        cache_key = f"{agent_id}:{query}"
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT context_data FROM persistent_context_cache WHERE cache_key = ? AND expiry_timestamp > ?",
                (cache_key, now)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_cached_context(self, agent_id: str, query_norm: str, result: str, ttl_seconds: int = 300) -> None:
        """Persist context result to SQLite with an expiry time."""
        expires_at = int(time.time()) + ttl_seconds
        # The cache_key is now a composite of agent_id and query_norm
        cache_key = f"{agent_id}:{query_norm}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO persistent_context_cache (cache_key, agent_id, query, context_data, expiry_timestamp)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET 
                    context_data = excluded.context_data,
                    expiry_timestamp = excluded.expiry_timestamp
                """,
                (cache_key, agent_id, query_norm, result, expires_at)
            )
            await db.commit()

    async def delete_cached_context(self, agent_id: str, query_norm: str) -> None:
        """Surgically remove a single cache entry."""
        cache_key = f"{agent_id}:{query_norm}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM persistent_context_cache WHERE cache_key = ?",
                (cache_key,)
            )
            await db.commit()

    async def clear_all_cached_context(self, agent_id: Optional[str] = None) -> int:
        """Clear all cache entries, optionally filtered by agent."""
        sql = "DELETE FROM persistent_context_cache"
        params = []
        if agent_id:
            sql += " WHERE agent_id = ?"
            params.append(agent_id)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, params) as cursor:
                rows_deleted = cursor.rowcount
            await db.commit()
            return rows_deleted

    async def create_seed_job(self, job_id: str, agent_id: str, urls: List[str]) -> None:
        """Initialize a new seeding job in the registry."""
        import json
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO seed_jobs (job_id, agent_id, status, urls, created_at, updated_at)
                VALUES (?, ?, 'PENDING', ?, ?, ?)
            """, (job_id, agent_id, json.dumps(urls), now, now))
            await db.commit()

    async def update_seed_job_status(self, job_id: str, status: str, results: Optional[dict] = None) -> None:
        """Update the status and results of a seeding job."""
        import json
        now = int(time.time())
        results_json = json.dumps(results) if results else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE seed_jobs SET status = ?, results = ?, updated_at = ?
                WHERE job_id = ?
            """, (status, results_json, now, job_id))
            await db.commit()

    async def get_seed_job(self, job_id: str) -> Optional[dict]:
        """Retrieve detailed status of a seeding job."""
        import json
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT * FROM seed_jobs WHERE job_id = ?", (job_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "job_id": row[0],
                        "agent_id": row[1],
                        "status": row[2],
                        "urls": json.loads(row[3]) if row[3] else [],
                        "results": json.loads(row[4]) if row[4] else None,
                        "created_at": row[5],
                        "updated_at": row[6]
                    }
                return None

    # --- LSA Storage Methods ---

    async def upsert_abstraction(self, a: Abstraction):
        """Creates or updates a structured abstraction node."""
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO abstractions (
                    id, agent_id, name, description, abstraction_type, source_refs,
                    support_count, confidence, invariants, variables, conditions,
                    effects, temporal_scope, succession_links, supersedes,
                    superseded_by, contention_group_id, decay_score,
                    created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    abstraction_type = excluded.abstraction_type,
                    source_refs = excluded.source_refs,
                    support_count = excluded.support_count,
                    confidence = excluded.confidence,
                    invariants = excluded.invariants,
                    variables = excluded.variables,
                    conditions = excluded.conditions,
                    effects = excluded.effects,
                    temporal_scope = excluded.temporal_scope,
                    succession_links = excluded.succession_links,
                    supersedes = excluded.supersedes,
                    superseded_by = excluded.superseded_by,
                    contention_group_id = excluded.contention_group_id,
                    decay_score = excluded.decay_score,
                    last_updated_at = excluded.last_updated_at
            """, (
                a.id, a.agent_id, a.name, a.description, a.abstraction_type, json.dumps(a.source_refs),
                a.support_count, a.confidence, json.dumps(a.invariants), json.dumps(a.variables),
                json.dumps(a.conditions), json.dumps(a.effects), json.dumps(a.temporal_scope),
                json.dumps(a.succession_links), a.supersedes, a.superseded_by, a.contention_group_id,
                a.decay_score, a.created_at, now
            ))
            await db.commit()

    async def get_abstraction(self, abstraction_id: str) -> Optional[Abstraction]:
        """Loads a structured abstraction from SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM abstractions WHERE id = ?", (abstraction_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                return Abstraction(
                    id=row["id"],
                    agent_id=row["agent_id"],
                    name=row["name"],
                    description=row["description"],
                    abstraction_type=row["abstraction_type"],
                    source_refs=json.loads(row["source_refs"]),
                    support_count=row["support_count"],
                    confidence=row["confidence"],
                    invariants=json.loads(row["invariants"]),
                    variables=json.loads(row["variables"]),
                    conditions=json.loads(row["conditions"]),
                    effects=json.loads(row["effects"]),
                    temporal_scope=json.loads(row["temporal_scope"]),
                    succession_links=json.loads(row["succession_links"]),
                    supersedes=row["supersedes"],
                    superseded_by=row["superseded_by"],
                    contention_group_id=row["contention_group_id"],
                    decay_score=row["decay_score"],
                    created_at=row["created_at"],
                    last_updated_at=row["last_updated_at"]
                )

    async def list_abstractions(self, agent_id: str) -> List[Abstraction]:
        """Lists all abstractions for an agent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM abstractions WHERE agent_id = ?", (agent_id,)) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    results.append(Abstraction(
                        id=row["id"],
                        agent_id=row["agent_id"],
                        name=row["name"],
                        description=row["description"],
                        abstraction_type=row["abstraction_type"],
                        source_refs=json.loads(row["source_refs"]),
                        support_count=row["support_count"],
                        confidence=row["confidence"],
                        invariants=json.loads(row["invariants"]),
                        variables=json.loads(row["variables"]),
                        conditions=json.loads(row["conditions"]),
                        effects=json.loads(row["effects"]),
                        temporal_scope=json.loads(row["temporal_scope"]),
                        succession_links=json.loads(row["succession_links"]),
                        supersedes=row["supersedes"],
                        superseded_by=row["superseded_by"],
                        contention_group_id=row["contention_group_id"],
                        decay_score=row["decay_score"],
                        created_at=row["created_at"],
                        last_updated_at=row["last_updated_at"]
                    ))
                return results

from typing import List, Optional
import sqlite3
import os
from .base import StorageProvider
from ..api.schemas import SearchResult, IngestRequest, ToolExecutionEvent, ToolStat
from ..core.config import settings

class StubRelationalProvider(StorageProvider):
    def __init__(self):
        db_path = "thalamus_rdbms.db" if not settings.sessions_dir else f"{settings.sessions_dir}/thalamus_rdbms.db"
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_stats (
                agent_id TEXT,
                tool_name TEXT,
                successes INTEGER DEFAULT 0,
                failures INTEGER DEFAULT 0,
                blocks INTEGER DEFAULT 0,
                PRIMARY KEY (agent_id, tool_name)
            )
        ''')
        self.conn.commit()

    async def record_tool_execution(self, event: ToolExecutionEvent) -> None:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO tool_stats (agent_id, tool_name)
            VALUES (?, ?)
        ''', (event.agent_id, event.tool_name))
        
        if event.status == "success":
            cursor.execute('UPDATE tool_stats SET successes = successes + 1 WHERE agent_id = ? AND tool_name = ?', (event.agent_id, event.tool_name))
        elif event.status == "blocked":
            cursor.execute('UPDATE tool_stats SET blocks = blocks + 1 WHERE agent_id = ? AND tool_name = ?', (event.agent_id, event.tool_name))
        else:
            cursor.execute('UPDATE tool_stats SET failures = failures + 1 WHERE agent_id = ? AND tool_name = ?', (event.agent_id, event.tool_name))
            
        self.conn.commit()

    async def get_tool_stats(self, agent_id: str) -> List[ToolStat]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT tool_name, successes, failures, blocks FROM tool_stats WHERE agent_id = ?', (agent_id,))
        rows = cursor.fetchall()
        return [
            ToolStat(tool_name=r[0], successes=r[1], failures=r[2], blocks=r[3])
            for r in rows
        ]

    async def search(self, query: str, limit: int) -> List[SearchResult]:
        return []

    async def add(self, request: IngestRequest) -> None:
        pass

    async def record_access(self, memory_id: str) -> None:
        pass

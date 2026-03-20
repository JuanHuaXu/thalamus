from typing import List, Optional
from pydantic import BaseModel, Field

class MemoryMessage(BaseModel):
    role: str
    content: str

class IngestRequest(BaseModel):
    agent_id: str
    conversation_id: Optional[str] = None
    messages: List[MemoryMessage]

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    min_score: float = 0.5

class ContextResponse(BaseModel):
    context: str
    metadata: dict = Field(default_factory=dict)

class SearchResult(BaseModel):
    path: str
    snippet: str
    score: float
    category: Optional[str] = None

class SyncRequest(BaseModel):
    agent_id: str
    session_id: Optional[str] = None
    deep_scan: bool = False

class SyncResponse(BaseModel):
    status: str
    messages_synced: int
    new_facts_extracted: int
    sessions_scanned: int

class ToolExecutionEvent(BaseModel):
    agent_id: str
    tool_name: str
    status: str # "success", "failed", "blocked"

class ToolStat(BaseModel):
    tool_name: str
    successes: int
    failures: int
    blocks: int

class ToolStatsResponse(BaseModel):
    agent_id: str
    stats: List[ToolStat]

class SeedRequest(BaseModel):
    urls: List[str]
    agent_id: str = "default"

class SeedResponse(BaseModel):
    status: str
    urls_processed: int
    facts_found: int

class SeedUndoRequest(BaseModel):
    agent_id: str

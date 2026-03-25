import time
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class MemoryMessage(BaseModel):
    role: str
    content: str

class IngestRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: Optional[str] = None
    messages: List[MemoryMessage]
    is_verified: bool = False

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

class DisputeRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    node_id: str

class BulkDisputeRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    query: str
    limit: int = 20

class PurgeRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    confirm: bool = False

class CompactRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    status_filter: str = "DISPUTED" # Can be DISPUTED or ARCHIVED

class SyncRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    session_id: Optional[str] = None
    deep_scan: bool = False

class SyncResponse(BaseModel):
    status: str
    messages_synced: int
    new_facts_extracted: int
    sessions_scanned: int

class ToolExecutionEvent(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    tool_name: str
    status: str # "success", "failed", "blocked"

class ToolStat(BaseModel):
    tool_name: str
    successes: int
    failures: int
    blocks: int

class ToolStatsResponse(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    stats: List[ToolStat]

class SeedRequest(BaseModel):
    urls: List[str]
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    content: Optional[str] = None # V1.9 Direct Ingestion Fallback

class SeedResponse(BaseModel):
    status: str
    job_id: str # V2.0 Tracking ID
    urls_submitted: int

class SeedJobStatus(BaseModel):
    job_id: str
    agent_id: str
    status: str
    urls: List[str]
    results: Optional[dict] = None
    created_at: int
    updated_at: int

class SeedUndoRequest(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")

# --- LSA Subsystem Schemas (Phase 2) ---

class AbstractionType(str, Enum):
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    EPISODIC = "episodic"
    RESIDUE = "residue"

class Abstraction(BaseModel):
    id: str
    agent_id: str
    name: str
    description: str
    abstraction_type: AbstractionType
    source_refs: List[str] = Field(default_factory=list)
    support_count: int = 1
    confidence: float = 0.5
    
    # Structural details
    invariants: List[str] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    conditions: List[str] = Field(default_factory=list)
    effects: List[str] = Field(default_factory=list)
    
    # Lifecycle & Temporal
    temporal_scope: Dict[str, Any] = Field(default_factory=dict)
    succession_links: Dict[str, Any] = Field(default_factory=dict) # e.g. {"next": [...], "prev": [...]}
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    contention_group_id: Optional[str] = None
    decay_score: float = 1.0
    
    created_at: int = Field(default_factory=lambda: int(time.time()))
    last_updated_at: int = Field(default_factory=lambda: int(time.time()))

class LSATrigger(BaseModel):
    agent_id: str
    abstraction_id: Optional[str] = None
    action: str # e.g. "create", "update", "merge", "split", "decay"
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)

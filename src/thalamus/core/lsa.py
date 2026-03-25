import logging
import json
import time
import uuid
import re
import httpx
from typing import List, Optional, Dict, Any
from ..api.schemas import Abstraction, AbstractionType, LSATrigger
from ..providers.cognee import CogneeProvider
from ..providers.relational import SQLiteRelationalProvider
from ..core.config import settings

logger = logging.getLogger(__name__)

class LSAEngine:
    """
    Subsystem for structured Latent Space Abstraction (LSA).
    Handles lifecycle operations: create, update, merge, split, decay, and contention.
    """
    
    def __init__(self, cognee: CogneeProvider, rdbms: SQLiteRelationalProvider):
        self.cognee = cognee
        self.rdbms = rdbms

    async def normalize_input(self, text: str) -> str:
        """Standardizes input text for pattern matching."""
        return text.strip().lower()

    async def emit_trigger(self, trigger: LSATrigger):
        """Emits an LSA event for external observability."""
        logger.info(f"[LSA] Event: {trigger.action} for {trigger.abstraction_id} (Agent: {trigger.agent_id})")
        # In a real system, this would push to a websocket or webhook
        pass

    async def detect_patterns(self, agent_id: str, cluster: List[str]) -> Optional[Abstraction]:
        """
        Uses LLM to discover a higher-level abstraction from a cluster of facts.
        """
        if not settings.llm_provider_url:
            return None
            
        prompt = (
            "Analyze these related facts and extract a single, structured abstraction object.\n"
            "Facts:\n" + "\n".join(cluster) + "\n\n"
            "Return a JSON object with: name, description, abstraction_type (semantic/procedural/episodic), "
            "invariants (list), variables (dict), conditions (list), effects (list)."
        )
        
        try:
            print(f"[LSA] Detecting patterns for {agent_id} with {len(cluster)} facts...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{settings.llm_provider_url.rstrip('/')}/api/generate", json={
                    "model": settings.llm_model_name,
                    "prompt": prompt,
                    "stream": False
                })
                resp.raise_for_status()
                raw_response = resp.json().get("response", "{}")
                print(f"[LSA] Raw LLM Response: {raw_response[:200]}...")
                
                # Try to extract JSON if it's wrapped in triple backticks
                json_match = re.search(r'```json\n(.*?)\n```', raw_response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(1))
                else:
                    data = json.loads(raw_response)
                
                return Abstraction(
                    id=f"abs_{uuid.uuid4().hex[:8]}",
                    agent_id=agent_id,
                    name=data.get("name", "Unnamed Abstraction"),
                    description=data.get("description", ""),
                    abstraction_type=data.get("abstraction_type", AbstractionType.SEMANTIC),
                    source_refs=cluster,
                    invariants=data.get("invariants", []),
                    variables=data.get("variables", {}),
                    conditions=data.get("conditions", []),
                    effects=data.get("effects", [])
                )
        except Exception as e:
            logger.error(f"[LSA] Pattern detection failed: {e}")
            if 'raw_response' in locals():
                logger.error(f"[LSA] Last raw response: {raw_response[:500]}")
            return None

    async def create_or_update_abstraction(self, abstraction: Abstraction):
        """Persists the abstraction."""
        await self.rdbms.upsert_abstraction(abstraction)
        await self.emit_trigger(LSATrigger(
            agent_id=abstraction.agent_id,
            abstraction_id=abstraction.id,
            action="update",
            message=f"Abstraction '{abstraction.name}' updated with confidence {abstraction.confidence}"
        ))

    async def process_evicted_context(self, agent_id: str, context_block: str):
        """
        Main entry point for pressure-driven eviction resynthesis.
        Distills raw evicted material into structured abstractions or residue.
        """
        logger.info(f"[LSA] Processing evicted context for {agent_id} ({len(context_block)} chars)")
        
        prompt = (
            "Analyze this evicted context and extract: \n"
            "1. Any stable abstractions (patterns, rules, facts).\n"
            "2. Any residue (raw context to be discarded or fast-decayed).\n"
            "3. Any unresolved loops or open questions.\n\n"
            f"Context:\n{context_block}\n\n"
            "Return a JSON object with keys: 'abstractions' (list of structured objects), "
            "'residue' (string), 'unresolved_loops' (list of strings)."
        )
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{settings.llm_provider_url.rstrip('/')}/api/generate", json={
                    "model": settings.llm_model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                })
                resp.raise_for_status()
                data = resp.json().get("response", "{}")
                if isinstance(data, str):
                    data = json.loads(data)
                
                # 1. Store stable abstractions
                for abs_data in data.get("abstractions", []):
                    new_abs = Abstraction(
                        id=f"abs_{uuid.uuid4().hex[:8]}",
                        agent_id=agent_id,
                        name=abs_data.get("name", "Distilled Abstraction"),
                        description=abs_data.get("description", ""),
                        abstraction_type=abs_data.get("abstraction_type", AbstractionType.SEMANTIC),
                        source_refs=["evicted_context_block"]
                    )
                    await self.rdbms.upsert_abstraction(new_abs)
                
                # 2. Handle residue (Placeholder: log it for now)
                residue = data.get("residue", "")
                if residue:
                    logger.info(f"[LSA] Residue preserved: {residue[:100]}...")
                
                # 3. Handle loops
                loops = data.get("unresolved_loops", [])
                for loop in loops:
                    await self.emit_trigger(LSATrigger(
                        trigger_type="unresolved_loop_detected",
                        message=f"Loop detected in evicted context: {loop}"
                    ))
                    
        except Exception as e:
            logger.error(f"[LSA] Eviction resynthesis failed: {e}")

    async def merge_abstractions(self, agent_id: str, abs_ids: List[str]):
        """Merges multiple overlapping abstractions into one."""
        if len(abs_ids) < 2: return
        
        objs = []
        for aid in abs_ids:
            obj = await self.rdbms.get_abstraction(aid)
            if obj: objs.append(obj)
            
        if not objs: return
        
        # Merge logic (simplified: use LLM to synthesize)
        # For now, we take the primary one and update its support count
        primary = objs[0]
        for other in objs[1:]:
            primary.support_count += other.support_count
            primary.confidence = min(1.0, primary.confidence + 0.1)
            primary.source_refs.extend(other.source_refs)
            # Mark others as superseded
            other.superseded_by = primary.id
            await self.rdbms.upsert_abstraction(other)
            
        primary.last_updated_at = int(time.time())
        await self.rdbms.upsert_abstraction(primary)
        
        # Assuming the first abstraction in objs is the 'target' and others are 'source'
        # This part is based on the provided code edit example, adapting to current function's variables
        target_id = primary.id
        source_ids = [obj.id for obj in objs[1:]] # IDs of abstractions merged into primary
        
        await self.emit_trigger(LSATrigger(
            agent_id=primary.agent_id, # Use primary's agent_id
            abstraction_id=target_id,
            action="merge",
            message=f"Merged {len(source_ids)} abstractions into {target_id}",
            payload={"merged_ids": source_ids}
        ))

    async def compute_decay(self, agent_id: str):
        """Updates decay scores for all abstractions of an agent."""
        abstractions = await self.rdbms.list_abstractions(agent_id)
        now = int(time.time())
        for a in abstractions:
            # Simple linear decay if not updated for > 24h
            if now - a.last_updated_at > 86400:
                a.decay_score *= 0.95
                a.confidence *= 0.98
                await self.rdbms.upsert_abstraction(a)

    async def split_abstraction(self, agent_id: str, abs_id: str):
        """
        Detects if an abstraction is overloaded and splits it into cleaner ones.
        """
        obj = await self.rdbms.get_abstraction(abs_id)
        if not obj: return
        
        # We check if source_refs are diverse enough to warrant a split
        if len(obj.source_refs) < 10: return # Only split well-supported nodes
        
        prompt = (
            f"Review this abstraction and determine if it represents multiple incompatible patterns.\n"
            f"Name: {obj.name}\n"
            f"Description: {obj.description}\n"
            f"Invariants: {obj.invariants}\n\n"
            "Return a JSON list of 2-3 new, more granular abstractions if a split is needed, "
            "otherwise return an empty list."
        )
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{settings.llm_provider_url.rstrip('/')}/api/generate", json={
                    "model": settings.llm_model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                })
                resp.raise_for_status()
                data = resp.json().get("response", "[]")
                if isinstance(data, str):
                    data = json.loads(data)
                
                if not data: return
                
                new_ids = []
                for item in data:
                    new_abs = Abstraction(
                        id=f"abs_{uuid.uuid4().hex[:8]}",
                        agent_id=agent_id,
                        name=item.get("name", obj.name + " (Split)"),
                        description=item.get("description", obj.description),
                        abstraction_type=obj.abstraction_type,
                        source_refs=obj.source_refs[0:len(obj.source_refs)//2], # Heuristic split
                        succession_links={"prev": [obj.id]}
                    )
                    await self.rdbms.upsert_abstraction(new_abs)
                    new_ids.append(new_abs.id)
                
                # Update original object
                obj.superseded_by = ",".join(new_ids)
                await self.rdbms.upsert_abstraction(obj)
                
                await self.emit_trigger(LSATrigger(
                    trigger_type="abstraction_split",
                    abstraction_id=obj.id,
                    message=f"Split overloaded abstraction {obj.id} into {len(new_ids)} granular nodes",
                    payload={"new_ids": new_ids}
                ))
        except Exception as e:
            logger.error(f"[LSA] Split failed: {e}")

    async def detect_contention(self, agent_id: str, query: str) -> List[str]:
        """
        Identifies abstractions that conflict for a given query.
        Returns a list of contention_group_ids.
        """
        # (Simplified: find abstractions with same name but different descriptions)
        abstractions = await self.rdbms.list_abstractions(agent_id)
        # Group by contention_group_id
        groups = {}
        for a in abstractions:
            if a.contention_group_id:
                groups.setdefault(a.contention_group_id, []).append(a.id)
        
        # If any group has multiple active members, it's a contention
        return [gid for gid, ids in groups.items() if len(ids) > 1]

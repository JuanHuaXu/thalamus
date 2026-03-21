import httpx
from typing import List
from .base import StorageProvider
from ..api.schemas import SearchResult, IngestRequest
from ..core.config import settings

class CogneeProvider(StorageProvider):
    def __init__(self):
        self.api_url = settings.cognee_api_url
        self.headers = {
            "Content-Type": "application/json",
            **( {"Authorization": f"Bearer {settings.cognee_api_key}"} if settings.cognee_api_key else {} )
        }

    async def search(self, query: str, limit: int, dataset_name: Optional[str] = None) -> List[SearchResult]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "query": query,
                "search_type": "GRAPH_COMPLETION",
                "limit": limit
            }
            if dataset_name:
                payload["dataset_names"] = [dataset_name]
                print(f"[Cognee] Searching {query} in dataset: {dataset_name}", flush=True)

            response = await client.post(
                f"{self.api_url}/api/v1/search",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            results = response.json()
            
            search_results = []
            for res in (results or []):
                if isinstance(res, str):
                    search_results.append(SearchResult(
                        path="graph_completion",
                        snippet=res,
                        score=1.0,
                        category="SYNTHESIS"
                    ))
                else:
                    search_results.append(SearchResult(
                        path=res.get("metadata", {}).get("path", "unknown") if isinstance(res.get("metadata"), dict) else "unknown",
                        snippet=res.get("text", res.get("snippet", str(res))),
                        score=res.get("score", 1.0),
                        category=res.get("metadata", {}).get("category") if isinstance(res.get("metadata"), dict) else None
                    ))
            return search_results

    async def add(self, request: IngestRequest) -> None:
        """Standard ingestion for conversation messages."""
        content = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
        await self.add_text(content, dataset_name=f"agent_{request.agent_id}")

    async def add_text(self, text: str, dataset_name: str) -> None:
        """Uploads a text block as a 'file' to Cognee."""
        # Increased timeout to 60s to handle Cognee processing
        from time import time
        timestamp = int(time())
        filename = f"ingest_{timestamp}.txt"
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                "data": (filename, text, "text/plain")
            }
            data = {"datasetName": dataset_name}
            
            print(f"[Cognee] Uploading {filename} to {dataset_name}", flush=True)
            response = await client.post(
                f"{self.api_url}/api/v1/add",
                headers={k: v for k, v in self.headers.items() if k != "Content-Type"},
                files=files,
                data=data
            )
            response.raise_for_status()

    async def record_access(self, memory_id: str) -> None:
        """Placeholder for auditing and freshness weighting."""
        pass

    async def cognify(self, dataset_name: str) -> None:
        """Triggers graph processing for the specified dataset."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/api/v1/cognify",
                headers=self.headers,
                json={"datasets": [dataset_name]}
            )
            response.raise_for_status()

    async def delete_agent_datasets(self, agent_id: str):
        """Discovers and deletes all Cognee datasets related to an agent (chat & seeds)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Fetch current datasets
            resp = await client.get(f"{self.api_url}/api/v1/datasets", headers=self.headers)
            resp.raise_for_status()
            datasets = resp.json()
            
            # 2. Filter by prefixes
            prefixes = [f"agent_{agent_id}", f"doc_seed_{agent_id}"]
            targets = [d for d in datasets if any(d.get("name", "").startswith(p) for p in prefixes)]
            
            # 3. Delete each target
            deleted_count = 0
            for target in targets:
                target_id = target.get("id")
                if target_id:
                    print(f"[Cognee] Permanently deleting dataset: {target.get('name')} ({target_id})", flush=True)
                    del_resp = await client.delete(f"{self.api_url}/api/v1/datasets/{target_id}", headers=self.headers)
                    if del_resp.status_code in (200, 204):
                        deleted_count += 1
            
            return deleted_count

    async def record_access(self, memory_id: str) -> None:
        # Cognee doesn't have a native 'record_access' yet, but we could update node metadata
        pass

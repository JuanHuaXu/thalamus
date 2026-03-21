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
            # We ignore dataset_name for the POST payload because the environment Cognee 
            # version throws 400 on 'dataset_names'. We filter in Thalamus instead.
            payload = {
                "query": query,
                "search_type": "GRAPH_COMPLETION",
                "limit": limit
            }

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
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                "data": ("ingest_chunk.txt", text, "text/plain")
            }
            data = {"datasetName": dataset_name}
            
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

    async def record_access(self, memory_id: str) -> None:
        # Cognee doesn't have a native 'record_access' yet, but we could update node metadata
        pass

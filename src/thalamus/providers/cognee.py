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

    async def search(self, query: str, limit: int) -> List[SearchResult]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/api/v1/search",
                headers=self.headers,
                json={
                    "query": query,
                    "search_type": "GRAPH", # Leverage graph by default
                    "limit": limit
                }
            )
            response.raise_for_status()
            results = response.json()
            
            return [
                SearchResult(
                    path=res.get("metadata", {}).get("path", "unknown"),
                    snippet=res.get("text", res.get("snippet", "")),
                    score=res.get("score", 1.0),
                    category=res.get("metadata", {}).get("category")
                )
                for res in (results or [])
            ]

    async def add(self, request: IngestRequest) -> None:
        async with httpx.AsyncClient() as client:
            # For simplicity in MVP, we send the content as a single blob to /add
            # In a real scenario, we might want to split messages or use multipart
            content = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
            
            # Cognee 'add' typically expects multipart-form-data for files
            files = {
                "data": (f"session_{request.agent_id}.txt", content, "text/plain")
            }
            dataset_name = settings.cognee_dataset_name if settings.cognee_dataset_name else f"agent_{request.agent_id}"
            data = {"datasetName": dataset_name}
            
            response = await client.post(
                f"{self.api_url}/api/v1/add",
                headers={k: v for k, v in self.headers.items() if k != "Content-Type"}, # httpx handles boundary
                files=files,
                data=data
            )
            response.raise_for_status()
            
            # Trigger cognify to process the new data
            await client.post(
                f"{self.api_url}/api/v1/cognify",
                headers=self.headers,
                json={"datasets": [dataset_name]}
            )

    async def record_access(self, memory_id: str) -> None:
        # Cognee doesn't have a native 'record_access' yet, but we could update node metadata
        pass

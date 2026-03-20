from abc import ABC, abstractmethod
from typing import List
from ..api.schemas import SearchResult, IngestRequest

class StorageProvider(ABC):
    @abstractmethod
    async def search(self, query: str, limit: int) -> List[SearchResult]:
        pass

    @abstractmethod
    async def add(self, request: IngestRequest) -> None:
        pass

    @abstractmethod
    async def record_access(self, memory_id: str) -> None:
        """For auditing and freshness weighting"""
        pass

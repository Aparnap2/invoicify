"""
RAG Client for Voice Agent.

Adapter pattern:
- Local: Qdrant (Docker) + Ollama embeddings
- Production: Azure AI Search (50MB free tier)

Usage:
    from src.voice.rag_client import PolicySearchClient
    
    client = PolicySearchClient()
    results = await client.search_policies("SLA requirements")
"""

import os
import structlog
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

logger = structlog.get_logger()

ENV = os.getenv("ENVIRONMENT", "local")


class SearchProvider(ABC):
    """Abstract base class for search providers."""
    
    @abstractmethod
    async def search(self, query: str, top_k: int = 3) -> List[str]:
        """Search for relevant documents."""
        pass
    
    @abstractmethod
    async def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """Index a document."""
        pass


class QdrantSearchProvider(SearchProvider):
    """Local Qdrant search provider with Ollama embeddings."""
    
    def __init__(self, qdrant_url: str = "http://qdrant:6333"):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=qdrant_url)
        self.collection_name = "procurement-policies"
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        
        # Initialize collection
        self._initialize_collection()
    
    def _initialize_collection(self):
        """Create collection if it doesn't exist."""
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "size": 768,  # nomic-embed-text dimension
                    "distance": "Cosine",
                },
            )
            logger.info("qdrant_collection_created", name=self.collection_name)
        except Exception as e:
            if "already exists" not in str(e):
                raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding from Ollama."""
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "prompt": text,
                },
            )
            response.raise_for_status()
            return response.json()["embedding"]
    
    async def search(self, query: str, top_k: int = 3) -> List[str]:
        """Search Qdrant for relevant documents."""
        # Get query embedding
        query_vector = await self._get_embedding(query)
        
        # Search
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
        )
        
        # Extract content from payloads
        chunks = [hit.payload.get("content", "") for hit in results if hit.payload]
        logger.info("qdrant_search_completed", query=query, results=len(chunks))
        
        return chunks
    
    async def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """Index a document in Qdrant."""
        # Get document embedding
        doc_vector = await self._get_embedding(content)
        
        # Upsert
        self.client.upsert(
            collection_name=self.collection_name,
            points=[{
                "id": doc_id,
                "vector": doc_vector,
                "payload": {
                    "content": content,
                    **metadata,
                },
            }],
        )
        
        logger.info("qdrant_document_indexed", doc_id=doc_id)


class AzureSearchProvider(SearchProvider):
    """Production Azure AI Search provider."""
    
    def __init__(self):
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        
        endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        key = os.getenv("AZURE_SEARCH_KEY")
        index_name = os.getenv("AZURE_SEARCH_INDEX", "procurement-policies")
        
        if not endpoint or not key:
            raise ValueError("AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY required")
        
        self.client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(key),
        )
    
    async def search(self, query: str, top_k: int = 3) -> List[str]:
        """Search Azure AI Search."""
        results = self.client.search(
            search_text=query,
            top=top_k,
        )
        
        chunks = [doc.get("content", "") for doc in results]
        logger.info("azure_search_completed", query=query, results=len(chunks))
        
        return chunks
    
    async def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """Index a document in Azure AI Search."""
        documents = [{
            "id": doc_id,
            "content": content,
            **metadata,
        }]
        
        self.client.upload_documents(documents)
        logger.info("azure_document_indexed", doc_id=doc_id)


class PolicySearchClient:
    """
    Unified RAG client for policy search.
    
    Automatically uses Qdrant (local) or Azure AI Search (production)
    based on ENVIRONMENT variable.
    """
    
    def __init__(self):
        if ENV == "local":
            logger.info("using_local_rag_provider", provider="qdrant")
            self.provider = QdrantSearchProvider()
        else:
            logger.info("using_azure_rag_provider", provider="azure_ai_search")
            self.provider = AzureSearchProvider()
    
    async def search_policies(self, query: str, top_k: int = 3) -> str:
        """
        Search procurement policies.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            Concatenated string of relevant policy chunks
        """
        chunks = await self.provider.search(query, top_k)
        
        if not chunks:
            return "No relevant policy information found."
        
        # Concatenate chunks with separators
        result = "\n\n---\n\n".join(chunks)
        
        logger.info(
            "policy_search_completed",
            query=query,
            chunks_found=len(chunks),
            result_length=len(result),
        )
        
        return result
    
    async def index_policy_document(
        self,
        doc_id: str,
        content: str,
        doc_type: str = "policy",
        category: Optional[str] = None,
    ):
        """
        Index a policy document.
        
        Args:
            doc_id: Document ID
            content: Document content
            doc_type: Document type (policy, procedure, guideline)
            category: Optional category
        """
        metadata = {
            "doc_type": doc_type,
            "category": category or "general",
            "indexed_at": "now",
        }
        
        await self.provider.index_document(doc_id, content, metadata)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────

_policy_client: Optional[PolicySearchClient] = None


def get_policy_search_client() -> PolicySearchClient:
    """Get or create policy search client singleton."""
    global _policy_client
    if _policy_client is None:
        _policy_client = PolicySearchClient()
    return _policy_client


async def search_procurement_policies(query: str) -> str:
    """
    Search procurement policies.
    
    Usage:
        results = await search_procurement_policies("SLA requirements")
    """
    client = get_policy_search_client()
    return await client.search_policies(query)


async def index_policy(doc_id: str, content: str, **metadata):
    """
    Index a policy document.
    
    Usage:
        await index_policy("sla-policy", "Our SLA requires...")
    """
    client = get_policy_search_client()
    await client.index_policy_document(doc_id, content, **metadata)

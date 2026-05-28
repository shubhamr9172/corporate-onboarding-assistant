import os
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List
from redis import Redis
from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger("app.cache")

# Configurations
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = 86400  # 24 hours
SIMILARITY_THRESHOLD = 0.92  # COSINE similarity limit

# Lazy connections
_redis_client = None
_embeddings = None
_chroma_cache_collection = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(REDIS_URL, socket_connect_timeout=2.0)
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis is down: {e}. L1 caching bypassed.")
            _redis_client = False
    return _redis_client

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        try:
            google_key = os.getenv("GOOGLE_API_KEY")
            _embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",
                google_api_key=google_key
            )
        except Exception as e:
            logger.error(f"Failed to initialize embeddings for L2 Cache: {e}")
    return _embeddings

def get_chroma_cache_collection():
    global _chroma_cache_collection
    if _chroma_cache_collection is None:
        try:
            from utils.chroma_manager import get_chroma_client
            client = get_chroma_client()
            # Fetch or create the semantic cache collection
            # Cosine distance = 1 - Cosine similarity
            # Distance should be <= 0.08 for similarity >= 0.92
            _chroma_cache_collection = client.get_or_create_collection(
                name="onboarding_semantic_cache",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB cache collection: {e}")
    return _chroma_cache_collection


def normalize_query(query: str) -> str:
    """Normalizes whitespace and capitalization of user query for cache hashing."""
    return " ".join(query.strip().lower().split())

def hash_query(query: str) -> str:
    """Returns SHA-256 hash of normalized query."""
    return hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()

def get_l1_cache(query: str, user_role: str) -> Optional[Dict[str, Any]]:
    """
    Checks L1 (Redis Exact Match) Cache.
    Returns dict with 'response' and 'source_docs' if hit, else None.
    Partitions cache entries by user_role for security (Issue #1).
    """
    client = get_redis_client()
    if client is False or client is None:
        return None
        
    q_hash = hash_query(query)
    key = f"cache:l1:{user_role}:{q_hash}"
    try:
        data = client.get(key)
        if data:
            logger.info(f"L1 Cache Hit! (Role: {user_role})")
            return json.loads(data)
    except Exception as e:
        logger.error(f"L1 Cache lookup failed: {e}")
    return None

def set_l1_cache(query: str, response: str, source_docs: List[Dict[str, Any]], user_role: str):
    """Caches query response in L1 (Redis) with role partition (Issue #1)."""
    client = get_redis_client()
    if client is False or client is None:
        return
        
    q_hash = hash_query(query)
    key = f"cache:l1:{user_role}:{q_hash}"
    try:
        val = json.dumps({"response": response, "source_docs": source_docs})
        client.set(key, val, ex=CACHE_TTL_SECONDS)
        logger.debug(f"L1 Cache stored successfully for role {user_role}.")
    except Exception as e:
        logger.error(f"Failed to store in L1 Cache: {e}")

def get_l2_cache(query: str, query_vector: List[float], user_role: str) -> Optional[Dict[str, Any]]:
    """
    Checks L2 (ChromaDB Semantic Similarity Match) Cache.
    Reuses precalculated query vector to avoid duplicate embedding API calls (Latency Optimization).
    Restricts search to entries matching user_role to prevent privilege leaks (Issue #1).
    """
    collection = get_chroma_cache_collection()
    if collection is None:
        return None
        
    try:
        normalized = normalize_query(query)
        
        # Search the Chroma cache collection filtering by user_role (Issue #1)
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=1,
            where={"user_role": user_role},
            include=["documents", "metadatas", "distances"]
        )
        
        # Verify results exist
        if results and results["documents"] and len(results["documents"][0]) > 0:
            distance = results["distances"][0][0]
            # Since space is cosine, cosine_similarity = 1 - cosine_distance
            similarity = 1.0 - distance
            
            if similarity >= SIMILARITY_THRESHOLD:
                logger.info(f"L2 Cache Hit! (Role: {user_role}, Similarity: {similarity:.4f})")
                meta = results["metadatas"][0][0]
                response = meta["response"]
                source_docs = json.loads(meta["source_docs"])
                return {"response": response, "source_docs": source_docs}
                
    except Exception as e:
        logger.error(f"L2 Cache lookup failed: {e}")
    return None

def set_l2_cache(query: str, response: str, source_docs: List[Dict[str, Any]], query_vector: List[float], user_role: str):
    """Caches query response in L2 ChromaDB with role partitioning (Issue #1)."""
    collection = get_chroma_cache_collection()
    if collection is None:
        return
        
    try:
        normalized = normalize_query(query)
        q_hash = hash_query(query)
        
        metadata = {
            "query": normalized,
            "response": response,
            "source_docs": json.dumps(source_docs),
            "user_role": user_role  # Tag cache item with role (Issue #1)
        }
        
        # Add to collection
        collection.add(
            ids=[q_hash],
            embeddings=[query_vector],
            documents=[normalized],
            metadatas=[metadata]
        )
        logger.debug(f"L2 Cache stored successfully for role {user_role}.")
    except Exception as e:
        logger.error(f"Failed to store in L2 Cache: {e}")

def get_cached_response(query: str, query_vector: List[float], user_role: str) -> Optional[Dict[str, Any]]:
    """
    Checks L1 and L2 caches sequentially with role isolation (Issue #1).
    Updates L1 if L2 hits.
    """
    # 1. Check L1 Cache
    hit = get_l1_cache(query, user_role)
    if hit:
        return hit
        
    # 2. Check L2 Cache
    hit = get_l2_cache(query, query_vector, user_role)
    if hit:
        # Repopulate L1 Cache for fast subsequent exact hits
        set_l1_cache(query, hit["response"], hit["source_docs"], user_role)
        return hit
        
    return None

def add_to_caches(query: str, response: str, source_docs: List[Dict[str, Any]], query_vector: List[float], user_role: str):
    """Stores query response in both L1 (Redis) and L2 (ChromaDB) caches with role validation."""
    set_l1_cache(query, response, source_docs, user_role)
    set_l2_cache(query, response, source_docs, query_vector, user_role)

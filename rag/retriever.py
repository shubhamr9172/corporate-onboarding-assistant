import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import chromadb

logger = logging.getLogger("app.retriever")

# Configurations
PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
    "chroma_db"
)
FAQ_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
    "data", 
    "onboarding_faq.txt"
)

# Lazy initialized clients
_embeddings = None
_chroma_client = None
_faq_collection = None
_ranker = None

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
            logger.error(f"Failed to initialize embeddings in retriever: {e}")
    return _embeddings

def get_chroma_collection():
    global _chroma_client, _faq_collection
    if _faq_collection is None:
        try:
            from utils.chroma_manager import get_chroma_client
            _chroma_client = get_chroma_client()
            _faq_collection = _chroma_client.get_collection("onboarding_faq_collection")
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB collection: {e}. Fallback triggered.")
            _faq_collection = None
    return _faq_collection


def get_ranker():
    global _ranker
    if _ranker is None:
        try:
            from flashrank import Ranker
            # Initialize lightweight local reranker
            # Downloads a small 4MB model to cache on first use
            _ranker = Ranker()
            logger.info("FlashRank Reranker initialized successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialize FlashRank: {e}. Rerank step will be bypassed.")
            _ranker = False
    return _ranker

def fallback_local_retrieval(query: str) -> List[Dict[str, Any]]:
    """
    Scans data/onboarding_faq.txt for keywords matching query to return fallback context.
    Prevents crash if ChromaDB is unreachable.
    """
    logger.info("Executing offline keyword fallback retrieval...")
    if not os.path.exists(FAQ_FILE_PATH):
        logger.error(f"Fallback file not found at: {FAQ_FILE_PATH}")
        return []
        
    try:
        with open(FAQ_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Segment file by double newlines or headers
        sections = re.split(r'\n=+\n|\[Category:', content)
        matched_chunks = []
        
        # Clean query words (remove punctuation, split)
        words = [w.lower() for w in re.findall(r'\b\w{3,}\b', query)]
        if not words:
            # Default fallback search words if query is short
            words = ["laptop", "leave", "salary", "medical"]
            
        for sect in sections:
            sect_clean = sect.strip()
            if not sect_clean:
                continue
                
            # Score section based on word count overlaps
            score = 0
            for word in words:
                if word in sect_clean.lower():
                    score += 1
                    
            if score > 0:
                matched_chunks.append({
                    "text": sect_clean,
                    "meta": {"source": "onboarding_faq.txt (Offline Fallback)", "score_weight": score}
                })
                
        # Sort chunks by count of matching words descending
        matched_chunks.sort(key=lambda x: x["meta"]["score_weight"], reverse=True)
        
        # Return top 3 chunks
        return matched_chunks[:3]
    except Exception as e:
        logger.error(f"Critical failure reading fallback file: {e}")
        return []

def retrieve_and_rerank(
    query: str, 
    user_role: str, 
    query_vector: Optional[List[float]] = None, 
    num_chunks: int = 3
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Retrieves top 10 chunks from ChromaDB filtering by role permissions (Issue #2),
    reranks them using FlashRank, and returns the top `num_chunks`.
    Reuses query_vector if provided to optimize latency.
    Returns (results_list, degraded_flag).
    """
    collection = get_chroma_collection()
    embeddings = get_embeddings()
    
    # Check if database is down
    if collection is None or embeddings is None:
        return fallback_local_retrieval(query), True
        
    try:
        # 1. Embed query if not pre-calculated
        if query_vector is None:
            query_vector = embeddings.embed_query(query)
            
        # 2. Build authorization roles check (Issue #2)
        where_filter = None
        if user_role != "admin":
            authorized_roles = ["joinee"]
            if user_role == "HR":
                authorized_roles = ["joinee", "HR"]
            where_filter = {"required_role": {"$in": authorized_roles}}
            
        # 3. Vector Search (Pull top 10 for reranking with role filters)
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=10,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results or not results["documents"] or len(results["documents"][0]) == 0:
            logger.warning("No matches found in ChromaDB. Falling back.")
            return fallback_local_retrieval(query), False
            
        # Parse documents into FlashRank format
        passages = []
        for i in range(len(results["documents"][0])):
            doc_text = results["documents"][0][i]
            meta = results["metadatas"][0][i] or {}
            # Standardize source metadata
            meta["source"] = meta.get("source", "Unknown Document")
            passages.append({
                "id": f"doc_{i}",
                "text": doc_text,
                "meta": meta
            })
            
        # 3. Reranking (using FlashRank)
        ranker = get_ranker()
        if ranker is False or ranker is None:
            # Bypass rerank if ranker fails to initialize
            logger.info("Bypassing rerank, serving raw semantic search results.")
            output = [{"text": p["text"], "meta": p["meta"]} for p in passages[:num_chunks]]
            return output, False
            
        from flashrank import RerankRequest
        rerank_request = RerankRequest(query=query, passages=passages)
        rerank_results = ranker.rerank(rerank_request)
        
        # Extract top candidates
        output_chunks = []
        for res in rerank_results[:num_chunks]:
            output_chunks.append({
                "text": res["text"],
                "meta": res["meta"]
            })
            
        return output_chunks, False
        
    except Exception as e:
        logger.error(f"Error during vector store retrieval pipeline: {e}. Triggering fallback.")
        return fallback_local_retrieval(query), True

import pytest
from unittest.mock import MagicMock, patch
from utils.cache import get_cached_response, add_to_caches, normalize_query, hash_query

def test_cache_helpers_normalize_and_hash():
    assert normalize_query("  Hello   World  ") == "hello world"
    assert len(hash_query("Hello")) == 64  # SHA-256 is 64 hex characters

def test_get_cached_response_l1_hit():
    mock_redis = MagicMock()
    # Mock exact match L1 cache hit
    mock_redis.get.return_value = b'{"response": "Cached answer", "source_docs": []}'
    
    with patch("utils.cache.get_redis_client", return_value=mock_redis):
        # We pass role partition "joinee"
        hit = get_cached_response("some query", [0.1, 0.2], "joinee")
        assert hit is not None
        assert hit["response"] == "Cached answer"
        
        # Verify L1 lookup is partitioned by role
        q_hash = hash_query("some query")
        mock_redis.get.assert_called_with(f"cache:l1:joinee:{q_hash}")

def test_get_cached_response_l2_semantic_hit():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # L1 miss
    
    # Mock L2 Chroma collection hit
    mock_collection = MagicMock()
    # Cosine distance = 0.05, so similarity = 0.95 >= threshold 0.92
    mock_collection.query.return_value = {
        "documents": [["some query"]],
        "metadatas": [[{
            "query": "some query",
            "response": "Semantic cache answer",
            "source_docs": "[]"
        }]],
        "distances": [[0.05]]
    }
    
    with patch("utils.cache.get_redis_client", return_value=mock_redis), \
         patch("utils.cache.get_chroma_cache_collection", return_value=mock_collection):
         
        hit = get_cached_response("some query", [0.1, 0.2], "joinee")
        assert hit is not None
        assert hit["response"] == "Semantic cache answer"
        
        # Verify L2 query called with user_role constraint
        mock_collection.query.assert_called_once()
        args, kwargs = mock_collection.query.call_args
        assert kwargs["where"] == {"user_role": "joinee"}
        assert kwargs["query_embeddings"] == [[0.1, 0.2]]
        
        # Verify it propagated back to L1 cache partitioned by role
        q_hash = hash_query("some query")
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == f"cache:l1:joinee:{q_hash}"

def test_add_to_caches():
    mock_redis = MagicMock()
    mock_collection = MagicMock()
    
    with patch("utils.cache.get_redis_client", return_value=mock_redis), \
         patch("utils.cache.get_chroma_cache_collection", return_value=mock_collection):
         
        add_to_caches("new query", "new response", [], [0.5, 0.6], "HR")
        
        # Verify added to L1
        q_hash = hash_query("new query")
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == f"cache:l1:HR:{q_hash}"
        
        # Verify added to L2 with user_role metadata
        mock_collection.add.assert_called_once()
        args, kwargs = mock_collection.add.call_args
        assert kwargs["ids"] == [q_hash]
        assert kwargs["embeddings"] == [[0.5, 0.6]]
        assert kwargs["metadatas"] == [{
            "query": "new query",
            "response": "new response",
            "source_docs": "[]",
            "user_role": "HR"
        }]

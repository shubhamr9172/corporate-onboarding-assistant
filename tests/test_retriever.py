import pytest
from unittest.mock import MagicMock, patch
from rag.retriever import retrieve_and_rerank


def test_retriever_role_filters_joinee():
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["docs"]],
        "metadatas": [[{"source": "doc1.txt"}]],
        "distances": [[0.1]],
    }
    mock_embeddings = MagicMock()

    with patch(
        "rag.retriever.get_chroma_collection", return_value=mock_collection
    ), patch("rag.retriever.get_embeddings", return_value=mock_embeddings), patch(
        "rag.retriever.get_ranker", return_value=False
    ):  # Bypass reranker

        # When user is joinee
        results, degraded = retrieve_and_rerank(
            "hello query", "joinee", query_vector=[0.1, 0.2]
        )

        # Verify query checks authorization metadata filter for joinee
        args, kwargs = mock_collection.query.call_args
        assert kwargs["where"] == {"required_role": {"$in": ["joinee"]}}
        assert kwargs["query_embeddings"] == [[0.1, 0.2]]


def test_retriever_role_filters_hr():
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["docs"]],
        "metadatas": [[{"source": "doc1.txt"}]],
        "distances": [[0.1]],
    }
    mock_embeddings = MagicMock()

    with patch(
        "rag.retriever.get_chroma_collection", return_value=mock_collection
    ), patch("rag.retriever.get_embeddings", return_value=mock_embeddings), patch(
        "rag.retriever.get_ranker", return_value=False
    ):

        # When user is HR
        results, degraded = retrieve_and_rerank(
            "hello query", "HR", query_vector=[0.1, 0.2]
        )

        # Verify query checks authorization metadata filter for joinee + HR
        args, kwargs = mock_collection.query.call_args
        assert kwargs["where"] == {"required_role": {"$in": ["joinee", "HR"]}}


def test_retriever_role_filters_admin_bypass():
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["docs"]],
        "metadatas": [[{"source": "doc1.txt"}]],
        "distances": [[0.1]],
    }
    mock_embeddings = MagicMock()

    with patch(
        "rag.retriever.get_chroma_collection", return_value=mock_collection
    ), patch("rag.retriever.get_embeddings", return_value=mock_embeddings), patch(
        "rag.retriever.get_ranker", return_value=False
    ):

        # When user is admin
        results, degraded = retrieve_and_rerank(
            "hello query", "admin", query_vector=[0.1, 0.2]
        )

        # Verify admin has no where filter constraint (sees legacy and untagged documents too)
        args, kwargs = mock_collection.query.call_args
        assert kwargs.get("where") is None


def test_retriever_embedding_generation_fallback():
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["docs"]],
        "metadatas": [[{"source": "doc1.txt"}]],
        "distances": [[0.1]],
    }
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.9, 0.8]

    with patch(
        "rag.retriever.get_chroma_collection", return_value=mock_collection
    ), patch("rag.retriever.get_embeddings", return_value=mock_embeddings), patch(
        "rag.retriever.get_ranker", return_value=False
    ):

        # When no query_vector is provided, retriever must generate it using the embeddings client
        results, degraded = retrieve_and_rerank(
            "hello query", "joinee", query_vector=None
        )

        mock_embeddings.embed_query.assert_called_with("hello query")
        args, kwargs = mock_collection.query.call_args
        assert kwargs["query_embeddings"] == [[0.9, 0.8]]

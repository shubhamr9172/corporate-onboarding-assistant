import os
import chromadb
import logging

logger = logging.getLogger("app.chroma_manager")

_persistent_client = None

def get_chroma_client() -> chromadb.PersistentClient:
    """
    Returns a shared singleton instance of chromadb.PersistentClient
    to prevent lock contention and data races (Issue #10).
    """
    global _persistent_client
    if _persistent_client is None:
        try:
            # Determine path to chroma_db folder relative to project root
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            persist_dir = os.path.join(root_dir, "chroma_db")
            _persistent_client = chromadb.PersistentClient(path=persist_dir)
            logger.info(f"Shared ChromaDB PersistentClient initialized at: {persist_dir}")
        except Exception as e:
            logger.critical(f"Failed to initialize shared ChromaDB PersistentClient: {e}", exc_info=True)
            raise e
    return _persistent_client

import os
import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from graph.state import AgentState
from graph.edges import route_after_cache, route_after_intent, route_after_confidence
from graph.nodes import (
    cache_node,
    intent_node,
    rag_node,
    confidence_node,
    escalate_node,
    progress_node,
    respond_node,
)

logger = logging.getLogger("app.graph")


def create_onboarding_graph():
    """
    Assembles and compiles the multi-node onboarding workflow.
    Configures SqliteSaver checkpointer for state memory.
    """
    # 1. Instantiate the State Graph
    workflow = StateGraph(AgentState)

    # 2. Add Nodes
    workflow.add_node("cache_node", cache_node)
    workflow.add_node("intent_node", intent_node)
    workflow.add_node("rag_node", rag_node)
    workflow.add_node("confidence_node", confidence_node)
    workflow.add_node("escalate_node", escalate_node)
    workflow.add_node("progress_node", progress_node)
    workflow.add_node("respond_node", respond_node)

    # 3. Add Edges & Conditional Routing
    workflow.set_entry_point("cache_node")

    workflow.add_conditional_edges(
        "cache_node",
        route_after_cache,
        {"respond_node": "respond_node", "intent_node": "intent_node"},
    )

    workflow.add_conditional_edges(
        "intent_node",
        route_after_intent,
        {"escalate_node": "escalate_node", "rag_node": "rag_node"},
    )

    workflow.add_edge("rag_node", "confidence_node")

    workflow.add_conditional_edges(
        "confidence_node",
        route_after_confidence,
        {"escalate_node": "escalate_node", "progress_node": "progress_node"},
    )

    workflow.add_edge("progress_node", "respond_node")
    workflow.add_edge("escalate_node", "respond_node")
    workflow.add_edge("respond_node", END)

    # 4. Set up persistence checkpointer (thread-safe)
    # from_conn_string creates per-operation connections, preventing
    # 'database is locked' errors under concurrent Streamlit sessions
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(root_dir, "onboarding_history.db")

    try:
        import sqlite3

        conn = sqlite3.connect(db_path, check_same_thread=False)
        memory = SqliteSaver(conn)
        logger.info(f"Thread-safe SQLite checkpointer configured at: {db_path}")
    except Exception as e:
        logger.error(
            f"Failed to init SQLite checkpointer: {e}. Fallback to MemorySaver."
        )
        from langgraph.checkpoint.memory import MemorySaver

        memory = MemorySaver()

    # 5. Compile state graph
    app = workflow.compile(checkpointer=memory)
    logger.info("LangGraph workflow compiled successfully.")
    return app

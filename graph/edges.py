import logging
from graph.state import AgentState

logger = logging.getLogger("app.edges")


def route_after_cache(state: AgentState) -> str:
    """Routes based on L1/L2 cache hit/miss."""
    decision = state.get("route_decision", "cache_miss")
    if decision == "cache_hit":
        logger.info("Routing: Cache Hit -> respond_node")
        return "respond_node"
    else:
        logger.info("Routing: Cache Miss -> intent_node")
        return "intent_node"


def route_after_intent(state: AgentState) -> str:
    """Routes based on intent classification result."""
    intent = state.get("intent", "General")
    if intent == "OutOfScope":
        logger.info("Routing: Intent is OutOfScope -> escalate_node")
        return "escalate_node"
    else:
        logger.info(f"Routing: Intent is {intent} -> rag_node")
        return "rag_node"


def route_after_confidence(state: AgentState) -> str:
    """Routes based on answer confidence evaluation."""
    decision = state.get("route_decision", "progress")
    if decision == "escalate":
        logger.info("Routing: Low Confidence -> escalate_node")
        return "escalate_node"
    else:
        logger.info("Routing: High Confidence -> progress_node")
        return "progress_node"

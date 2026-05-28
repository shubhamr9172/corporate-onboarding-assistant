import pytest
from graph.edges import route_after_cache, route_after_intent, route_after_confidence

def test_route_after_cache():
    # Cache hit
    state_hit = {"route_decision": "cache_hit"}
    assert route_after_cache(state_hit) == "respond_node"

    # Cache miss
    state_miss = {"route_decision": "cache_miss"}
    assert route_after_cache(state_miss) == "intent_node"

    # Default fallback
    state_empty = {}
    assert route_after_cache(state_empty) == "intent_node"

def test_route_after_intent():
    # Out of scope
    state_oos = {"intent": "OutOfScope"}
    assert route_after_intent(state_oos) == "escalate_node"

    # In scope
    state_policy = {"intent": "Policy"}
    assert route_after_intent(state_policy) == "rag_node"

    # Default fallback
    state_empty = {}
    assert route_after_intent(state_empty) == "rag_node"

def test_route_after_confidence():
    # Escalate
    state_esc = {"route_decision": "escalate"}
    assert route_after_confidence(state_esc) == "escalate_node"

    # Progress
    state_prog = {"route_decision": "progress"}
    assert route_after_confidence(state_prog) == "progress_node"

    # Default fallback
    state_empty = {}
    assert route_after_confidence(state_empty) == "progress_node"

from typing import TypedDict, List, Dict, Optional, Any

class AgentState(TypedDict):
    session_id: str
    user_role: str                     # 'joinee' | 'HR' | 'manager'
    conversation_history: List[Dict[str, str]]  # list of {"role": "user"|"assistant", "content": str}
    current_message: str
    intent: str                        # 'General' | 'Followup' | 'OutOfScope'
    rag_answer: Optional[str]
    source_docs: List[Dict[str, Any]]  # List of dicts with {"text": text, "meta": {source, page...}}
    confidence_score: float
    route_decision: str                # 'cache_hit' | 'cache_miss' | 'escalate' | 'progress'
    escalation_summary: Optional[str]
    topics_covered: Dict[str, bool]    # {"Policy": bool, "Benefits": bool, "IT Setup": bool, "Team": bool, "Payroll": bool}
    token_usage: Dict[str, Any]        # {"input_tokens": int, "output_tokens": int, "total_cost_usd": float}
    query_embedding: Optional[List[float]] # Reusable precalculated embedding vector
    final_response: str


import os
import json
import logging
from typing import Dict, Any, List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from graph.state import AgentState
from prompts.prompts import INTENT_PROMPT, RAG_PROMPT, ESCALATION_PROMPT
from rag.retriever import retrieve_and_rerank
from utils.cache import get_cached_response, add_to_caches
from utils.progress import update_topics_covered

logger = logging.getLogger("app.nodes")

# Gemini pricing estimates ($ per million tokens) - Configurable via env (Issue #9)
GEMINI_INPUT_COST_M = float(os.getenv("GEMINI_INPUT_COST_M", "0.075"))
GEMINI_OUTPUT_COST_M = float(os.getenv("GEMINI_OUTPUT_COST_M", "0.30"))


# Initialize Model (Gemini 2.5 Flash)
def get_llm(temperature: float = 0.1):
    google_key = os.getenv("GOOGLE_API_KEY")
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=temperature,
        google_api_key=google_key,
        response_mime_type="application/json"
    )

def parse_token_usage(response) -> Tuple[int, int, float]:
    """Helper to extract token metrics and calculate approximate cost."""
    try:
        # Check standard langchain usage_metadata attribute
        usage = getattr(response, "usage_metadata", None) or {}
        if usage:
            input_tok = usage.get("input_tokens", 0)
            output_tok = usage.get("output_tokens", 0)
        else:
            # Fallback to response_metadata
            meta = response.response_metadata or {}
            usage_legacy = meta.get("token_usage", {})
            input_tok = usage_legacy.get("prompt_tokens", 0) or usage_legacy.get("input_tokens", 0) or 0
            output_tok = usage_legacy.get("completion_tokens", 0) or usage_legacy.get("output_tokens", 0) or 0
            
        cost = (input_tok * GEMINI_INPUT_COST_M / 1_000_000) + (output_tok * GEMINI_OUTPUT_COST_M / 1_000_000)
        return input_tok, output_tok, cost
    except Exception as e:
        logger.warning(f"Error parsing token usage metadata: {e}")
        return 0, 0, 0.0

def update_cost_metrics(state: AgentState, input_tokens: int, output_tokens: int, cost: float) -> Dict[str, Any]:
    """Increments the session's cumulative token usage and cost metrics."""
    usage = state.get("token_usage") or {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}
    usage["input_tokens"] += input_tokens
    usage["output_tokens"] += output_tokens
    usage["total_cost_usd"] += cost
    return usage

def format_history(history: List[Dict[str, str]]) -> str:
    """Formats chat history array into a readable string for LLM prompts."""
    formatted = []
    for turn in history:
        role = "User" if turn["role"] == "user" else "Assistant"
        formatted.append(f"{role}: {turn['content']}")
    return "\n".join(formatted) if formatted else "No history."

# ==============================================================================
# NODES
# ==============================================================================

def cache_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 0: Semantic/Exact cache check node.
    Bypasses LLM nodes on cache hits.
    """
    logger.info("Executing cache_node...")
    query = state.get("current_message", "")
    user_role = state.get("user_role", "joinee")
    
    # Generate query embedding vector once to reuse (Latency Optimization)
    query_vector = []
    try:
        from utils.cache import get_embeddings
        embeddings = get_embeddings()
        if embeddings:
            query_vector = embeddings.embed_query(query)
    except Exception as e:
        logger.error(f"Failed to generate query embedding in cache_node: {e}")

    # Check L1 / L2 Cache with precomputed vector and user_role filter (Issue #1)
    hit = None
    if query_vector:
        hit = get_cached_response(query, query_vector, user_role)
    else:
        # Fallback exact cache lookup if embedding fails
        from utils.cache import get_l1_cache
        hit = get_l1_cache(query, user_role)
        
    if hit:
        logger.info(f"Cache hit verified for role {user_role}. Bypassing LangGraph processing.")
        return {
            "final_response": hit["response"],
            "source_docs": hit["source_docs"],
            "route_decision": "cache_hit",
            "rag_answer": "",
            "escalation_summary": "",
            "confidence_score": 1.0,
            "query_embedding": query_vector
        }
        
    logger.info(f"Cache miss for role {user_role}. Routing query to safety/LLM pipelines.")
    return {
        "route_decision": "cache_miss",
        "final_response": "",
        "rag_answer": "",
        "escalation_summary": "",
        "confidence_score": 0.0,
        "source_docs": [],
        "query_embedding": query_vector
    }

def intent_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 1: Intent classification node.
    Categorizes query into General, Followup, or OutOfScope.
    """
    logger.info("Executing intent_node...")
    message = state.get("current_message", "")
    history = format_history(state.get("conversation_history", []))
    
    prompt = INTENT_PROMPT.format(history=history, message=message)
    
    try:
        llm = get_llm(temperature=0.1)
        response = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(response.content)
        
        intent = data.get("intent", "General")
        reason = data.get("reason", "")
        logger.info(f"Intent classified: {intent} (Reason: {reason})")
        
        in_t, out_t, cost = parse_token_usage(response)
        usage = update_cost_metrics(state, in_t, out_t, cost)
        
        return {
            "intent": intent,
            "token_usage": usage
        }
    except Exception as e:
        logger.error(f"Error during intent classification: {e}. Defaulting to 'General'.")
        return {
            "intent": "General"
        }

def rag_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 2: RAG vector store query and answering node.
    Retrieves, reranks context, and calls Gemini for grounding.
    """
    logger.info("Executing rag_node...")
    message = state.get("current_message", "")
    history = format_history(state.get("conversation_history", []))
    
    # Determine retrieval depth based on multi-part/follow-up indicators
    is_multipart = len(message.split("?")) > 2 or "and" in message.lower()
    depth = 5 if is_multipart else 3
    
    # 1. Retrieve chunks with reranking (Issue #2 and Latency Optimization)
    user_role = state.get("user_role", "joinee")
    query_vector = state.get("query_embedding")
    chunks, degraded = retrieve_and_rerank(message, user_role, query_vector=query_vector, num_chunks=depth)

    
    # Formulate documents metadata
    source_docs = []
    context_str = ""
    for idx, c in enumerate(chunks, 1):
        text = c["text"]
        meta = c["meta"] or {}
        source_name = meta.get("source", "onboarding_faq.txt")
        page_indicator = f" (Page {meta['page']})" if "page" in meta else ""
        
        source_docs.append({
            "index": idx,
            "source": f"{source_name}{page_indicator}",
            "text": text
        })
        context_str += f"[{idx}] Source: {source_name}{page_indicator}\nContent: {text}\n\n"
        
    if not context_str:
        context_str = "No relevant onboarding context found in database."
        
    # 2. Call LLM
    prompt = RAG_PROMPT.format(context=context_str, history=history, message=message)
    
    try:
        llm = get_llm(temperature=0.2)
        response = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(response.content)
        
        ans = data.get("answer", "I don't know the answer based on the onboarding files.")
        conf = float(data.get("confidence_score", 0.0))
        logger.info(f"RAG Node answer compiled. Confidence: {conf}")
        
        # If retriever failed/degraded, add notification message in UI
        if degraded:
            ans = "[⚠️ Service Degraded: Offline Backup Used]\n\n" + ans
            
        in_t, out_t, cost = parse_token_usage(response)
        usage = update_cost_metrics(state, in_t, out_t, cost)
        
        return {
            "rag_answer": ans,
            "confidence_score": conf,
            "source_docs": source_docs,
            "token_usage": usage
        }
    except Exception as e:
        logger.error(f"Error during RAG LLM call: {e}. Failing to escalation.")
        return {
            "rag_answer": "RAG answering service failed.",
            "confidence_score": 0.0,
            "source_docs": []
        }

def confidence_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 3: Non-LLM Confidence check node.
    Routes to escalation if confidence < 0.5.
    """
    logger.info("Executing confidence_node...")
    score = state.get("confidence_score", 0.0)
    
    if score >= 0.5:
        logger.info(f"Confidence score {score} >= 0.5. Routing to checklist progress.")
        return {"route_decision": "progress"}
    else:
        logger.info(f"Confidence score {score} < 0.5. Routing to HR Escalation.")
        return {"route_decision": "escalate"}

def escalate_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 4: LLM HR Escalation node.
    Synthesizes ticket request detail.
    """
    logger.info("Executing escalate_node...")
    message = state.get("current_message", "")
    history = format_history(state.get("conversation_history", []))
    
    prompt = ESCALATION_PROMPT.format(history=history, message=message)
    
    try:
        llm = get_llm(temperature=0.2)
        response = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(response.content)
        
        summary = data.get("escalation_summary", "Unable to answer onboarding question.")
        # Trigger operational alert for log monitoring tools (Issue #12)
        logger.critical(f"ALERT:HR_ESCALATION query='{message}' summary='{summary}'")
        
        in_t, out_t, cost = parse_token_usage(response)
        usage = update_cost_metrics(state, in_t, out_t, cost)
        
        escalated_text = (
            f"I apologize, but I cannot find a definitive answer to your question in our onboarding documents.\n\n"
            f"**HR Ticket Generated:**\n"
            f"*{summary}*\n\n"
            f"An HR support representative has been notified and will reach out to you directly."
        )

        
        return {
            "escalation_summary": summary,
            "final_response": escalated_text,
            "token_usage": usage
        }
    except Exception as e:
        logger.error(f"Error compiling escalation: {e}.")
        fallback_text = (
            "I'm unable to answer your query. I have created a generic support request with HR. "
            "Please check back later or email onboarding@company.com."
        )
        return {
            "escalation_summary": "General onboarding query escalation.",
            "final_response": fallback_text
        }

def progress_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 5: Non-LLM onboarding checklist progress node.
    Scans query for keywords to mark checklist tasks complete.
    """
    logger.info("Executing progress_node...")
    message = state.get("current_message", "")
    topics = state.get("topics_covered") or {
        "Policy": False, "Benefits": False, "IT Setup": False, "Team": False, "Payroll": False
    }
    
    updated = update_topics_covered(message, topics)
    return {
        "topics_covered": updated
    }

def respond_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 6: Assembler node.
    Cleans up response, compresses history, and populates caches.
    """
    logger.info("Executing respond_node...")
    
    # 1. Clean final response from RAG answer if not set by escalation
    final_resp = state.get("final_response", "")
    rag_ans = state.get("rag_answer")
    
    if not final_resp and rag_ans:
        final_resp = rag_ans
        
    # 2. History compilation & context compression (Issue #15)
    history = state.get("conversation_history") or []
    history.append({"role": "user", "content": state.get("current_message", "")})
    history.append({"role": "assistant", "content": final_resp})
    
    if len(history) > 10:
        logger.info(f"Conversation history size is {len(history)}. Compressing history using summarization.")
        to_summarize = history[:-4]
        to_keep = history[-4:]
        
        # Format conversation messages for the summarization prompt
        formatted_messages = []
        for msg in to_summarize:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted_messages.append(f"{role.capitalize()}: {content}")
        history_str = "\n".join(formatted_messages)
        
        prompt = (
            "Summarize the following conversation history between a new employee (Joinee) and an Onboarding Assistant.\n"
            "Focus on extracting key context such as user preferences, roles, completed setup tasks, and decisions.\n"
            "Keep the summary extremely concise (under 3 sentences).\n"
            "Return a JSON object with a single key 'summary'.\n\n"
            f"Conversation History:\n{history_str}"
        )
        try:
            llm = get_llm(temperature=0.0)
            response = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(response.content)
            summary_text = data.get("summary", "").strip()
            
            if summary_text:
                logger.info(f"Generated conversation summary: {summary_text}")
                history = [
                    {"role": "system", "content": f"Summary of earlier conversation: {summary_text}"}
                ] + to_keep
            else:
                # Fallback to naive truncation if summary is empty
                logger.warning("Empty summary generated. Falling back to naive truncation.")
                history = history[-10:]
        except Exception as e:
            logger.error(f"Error summarizing history: {e}. Falling back to naive truncation.")
            history = history[-10:]

        
    # 3. Store high-confidence answers back to L1/L2 caches
    # We only cache if:
    # - Route was not cache hit
    # - RAG answer is present
    # - Confidence is high (>= 0.8)
    route_decision = state.get("route_decision", "")
    confidence = state.get("confidence_score", 0.0)
    
    if route_decision != "cache_hit" and rag_ans and confidence >= 0.8:
        query = state.get("current_message", "")
        source_docs = state.get("source_docs", [])
        query_vector = state.get("query_embedding") or []
        user_role = state.get("user_role", "joinee")
        
        # If vector is somehow missing, regenerate it
        if not query_vector:
            try:
                from utils.cache import get_embeddings
                embeddings = get_embeddings()
                if embeddings:
                    query_vector = embeddings.embed_query(query)
            except Exception as e:
                logger.error(f"Failed to generate query embedding in respond_node: {e}")
                
        if query_vector:
            logger.info(f"Caching high confidence answer (Score: {confidence}, Role: {user_role}) in L1 & L2.")
            add_to_caches(query, final_resp, source_docs, query_vector, user_role)
        else:
            logger.warning("Could not cache high confidence answer due to missing embedding vector.")

        
    return {
        "final_response": final_resp,
        "conversation_history": history
    }

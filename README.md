# 🤖 Corporate Onboarding Assistant V2

Corporate Onboarding Assistant V2 is a stateful, multi-turn RAG chatbot guiding new hires through IT setup, leave policies, health insurance, and payroll.

---

## 🏗️ Architectural Flow

The request lifecycle is managed as a compiled state machine under **LangGraph**, ensuring memory persistence and context routing:

```mermaid
graph TD
    User([User Input]) --> RateLimit[Rate Limiter]
    RateLimit -->|Allow| CacheNode[0. Cache Node]
    RateLimit -->|Block| LimitExceeded[Rate Limit Exceeded Page]
    
    CacheNode -->|L1/L2 Cache Hit| RespondNode[6. Respond Node]
    CacheNode -->|Cache Miss| GuardrailInput[Input Guardrails]
    
    GuardrailInput -->|Safe / Budget OK| IntentNode[1. Intent Node]
    GuardrailInput -->|Unsafe / Budget Exceeded| EscalateNode[4. Escalate Node]
    
    IntentNode -->|OutOfScope| EscalateNode
    IntentNode -->|General / Followup| RAGNode[2. RAG Node]
    
    RAGNode --> ConfidenceNode[3. Confidence Node]
    
    ConfidenceNode -->|< 0.5 Threshold| EscalateNode
    ConfidenceNode -->|>= 0.5 Threshold| ProgressNode[5. Progress Node]
    
    EscalateNode --> RespondNode
    ProgressNode --> RespondNode
    
    RespondNode --> GuardrailOutput[Output Guardrails]
    GuardrailOutput -->|Checked| UI[Streamlit UI]
```

---

## ⚡ Hybrid Caching Strategy

The assistant implements L1/L2 cache layers to reduce token costs and minimize response latency:

```mermaid
graph TD
    Query([User Query]) --> L1{L1 Cache: Redis Exact Match}
    L1 -->|Hit| Respond[Serve Response < 5ms]
    L1 -->|Miss| L2{L2 Cache: ChromaDB Semantic}
    L2 -->|Hit: Similarity >= 0.92| SaveL1[Save to L1 Cache] --> Respond
    L2 -->|Miss| L3[L3 Graph Execution]
    L3 -->|Answer Confidence >= 0.8| SaveBoth[Save to L1 & L2 Caches] --> Respond
    L3 -->|Answer Confidence < 0.8| Respond
```

---

## 📚 Document Ingestion & RAG Pipeline

Documents are parsed, chunked, and embedded on-demand, then reranked during query retrieval:

```mermaid
graph TD
    subgraph Ingestion Pipeline
        Docs[data/ Documents] --> Parser[PDF / Word / Markdown / Text Parser]
        Parser --> Splitter[Recursive Character Splitter]
        Splitter --> Embedder[Gemini Embeddings]
        Embedder --> Chroma[(ChromaDB Vector Store)]
    end
    
    subgraph Query & RAG Pipeline
        UserQuery([User Query]) --> SemanticSearch[ChromaDB Search - Top 10 Chunks]
        Chroma -.-> SemanticSearch
        SemanticSearch --> Reranker[FlashRank CPU Reranker - Top 3 Chunks]
        Reranker --> LLM[Gemini 2.5 Flash Grounded QA]
        LLM --> UI[Final Citation Response]
    end
```

---

## 🔄 User Feedback Flywheel

Flags and ratings populate local feedback datastores and update automated test suites:

```mermaid
graph TD
    User([User Feedback: Thumbs Up / Down]) --> SQLite[(SQLite Feedback Logs DB)]
    User --> LangSmith[LangSmith Run Trace Update]
    SQLite --> Cron[Manual/Cron Trigger]
    Cron --> Benchmark[tests/test_dataset.json Updates]
    Benchmark --> Pytest[pytest tests/test_evals.py]
```

---

## 📂 Quick Reference Folder Structure

*   `app.py`: Streamlit frontend UI.
*   `graph/`: Graph orchestration (`state.py`, `nodes.py`, `edges.py`, `graph.py`).
*   `rag/`: Document parsers and rerankers (`ingest.py`, `retriever.py`).
*   `utils/`: Caching (`cache.py`), startup checker (`config_check.py`), rate-limiter (`rate_limiter.py`).
*   `guardrails/`: Safety PII and prompt injection filters (`guard.py`).
*   `tests/`: DeepEval automated RAG evaluations (`test_evals.py`).
*   `agents/`: Automated code static compliance auditor (`auditor.py`).

---

## 🚀 Quick Run Guide

### 1. Configure Environment
Create a `.env` in the root folder:
```ini
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
REDIS_URL=redis://localhost:6379/0
SESSION_BUDGET_USD=0.50
```

### 2. Start Services
Run Redis and install requirements:
```powershell
# 1. Activate Environment & Install requirements
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Run Redis Container
docker run -d --name local-redis -p 6379:6379 redis:7.2-alpine
```

### 3. Ingest Data & Launch Chat UI
```powershell
# 1. Ingest Raw Documents (from /data directory)
python rag/ingest.py

# 2. Launch Streamlit Chat Client
streamlit run app.py
```

---

## 🧪 Admin Compliance & Testing CLI Commands

| Action | Command | Expected Result |
| :--- | :--- | :--- |
| **Code Auditor** | `python agents/auditor.py` | Generates a static guidelines validation report `audit_report.json`. |
| **RAG Eval Tests** | `pytest tests/test_evals.py` | Executes DeepEval metrics (Faithfulness & Relevance) against benchmarks. |
| **GDPR PII Purge** | `python utils/purge_user.py <session_id>` | Deletes all checkpoints and logs matching a target session ID. |
| **30-Day Cleanup** | `python utils/prune_db.py` | Automatically wipes SQLite checkpoints older than 30 days. |

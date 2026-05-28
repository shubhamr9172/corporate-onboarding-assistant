import os
import json
import pytest
from dotenv import load_dotenv
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

# Load environment configuration
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(root_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_google_genai import ChatGoogleGenerativeAI
from graph.graph import create_onboarding_graph

# Configure custom Gemini model for DeepEval to avoid OpenAI key dependency
class GeminiEvalModel(DeepEvalBaseLLM):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1
        )
        
    def load_model(self):
        return self.model
        
    def generate(self, prompt: str) -> str:
        return self.model.invoke(prompt).content
        
    async def a_generate(self, prompt: str) -> str:
        res = await self.model.ainvoke(prompt)
        return res.content
        
    def get_model_name(self):
        return self.model_name

# Lazy initialization of evaluation resources
_eval_model = None
_graph_app = None

def get_eval_model():
    global _eval_model
    if _eval_model is None:
        _eval_model = GeminiEvalModel()
    return _eval_model

def get_graph():
    global _graph_app
    if _graph_app is None:
        _graph_app = create_onboarding_graph()
    return _graph_app

# Dummy dataset for default fallback tests
DEFAULT_TEST_CASES = [
    {
        "query": "How do I request my corporate laptop?",
        "expected_topic": "IT Setup"
    },
    {
        "query": "What is the policy for medical leave?",
        "expected_topic": "Policy"
    }
]

def load_test_cases():
    """Loads benchmark test cases from dataset or defaults."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_path = os.path.join(root_dir, "tests", "test_dataset.json")
    
    if os.path.exists(dataset_path):
        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                cases = json.load(f)
                return cases
        except Exception as e:
            print(f"Failed to parse existing test dataset: {e}")
    return DEFAULT_TEST_CASES

@pytest.mark.parametrize("case", load_test_cases())
def test_onboarding_responses(case):
    """
    RAG Quality Unit Tests.
    Executes the query, gathers generated response + chunks, and asserts
    faithfulness and relevance metrics via DeepEval on Gemini 2.5 Flash.
    """
    query = case.get("query") or case.get("input")
    
    # 1. Invoke LangGraph chatbot
    app = get_graph()
    import uuid
    session_id = f"test_eval_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": session_id}}
    
    state = {
        "current_message": query,
        "user_role": "joinee",
        "conversation_history": [],
        "topics_covered": {
            "Policy": False, "Benefits": False, "IT Setup": False, "Team": False, "Payroll": False
        },
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}
    }
    
    final_state = app.invoke(state, config)
    actual_output = final_state.get("final_response")
    source_docs = final_state.get("source_docs") or []
    
    # Format retrieved contexts for DeepEval
    retrieval_context = [doc["text"] for doc in source_docs]
    if not retrieval_context:
        retrieval_context = ["No document context retrieved."]
        
    # 2. Setup DeepEval metrics with our Gemini evaluator
    model = get_eval_model()
    
    faithfulness_metric = FaithfulnessMetric(threshold=0.7, model=model)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.7, model=model)
    
    # 3. Create DeepEval test case structure
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )
    
    # 4. Assert metrics
    assert_test(test_case, [faithfulness_metric, relevancy_metric])

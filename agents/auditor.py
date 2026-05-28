import os
import json
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Load environment configuration
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(root_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.auditor")

AUDIT_PROMPT = """
You are an expert AI Auditor and Software Architect. Your job is to review the code of the "Corporate Onboarding Assistant V2" project and verify compliance with production guidelines.

Analyze the provided source code files and output a JSON audit report.

Guidelines to verify:
1. Pure Python Rule Nodes: "confidence_node" and "progress_node" in graph/nodes.py MUST be pure Python and MUST NOT make LLM calls or reference ChatGoogleGenerativeAI/get_llm.
2. Prompts Isolation: All LLM prompts must reside strictly in prompts/prompts.py. Verify that nodes.py does not define hardcoded prompt strings.
3. Exception Handling: Nodes performing external API calls (intent_node, rag_node, escalate_node) must contain try-except blocks to fail gracefully and route to fallbacks rather than crashing.
4. Schema Integrity: Verify that graph/state.py contains session_id, user_role, topics_covered, and token_usage.
5. Code Quality: Flag redundant code, missing type hints, missing docstrings, or potential performance bottlenecks.

Respond ONLY in JSON matching this schema:
{{
  "compliance_score": <float between 0.0 and 1.0 indicating total compliance>,
  "findings": [
    {{
      "file": "path/to/file",
      "guideline": "Rule Nodes / Prompts / Exception / Schema / Quality",
      "severity": "CRITICAL" | "WARNING" | "INFO",
      "description": "Detailed explanation of the issue found",
      "recommendation": "Exactly how to fix it"
    }}
  ]
}}

Source Code Files:
{source_code}
"""

def load_codebase(root_dir: str) -> str:
    """Reads project code files and formats them into a single string for audit."""
    target_files = [
        "graph/state.py",
        "graph/nodes.py",
        "graph/edges.py",
        "graph/graph.py",
        "prompts/prompts.py",
        "rag/ingest.py",
        "rag/retriever.py",
        "guardrails/guard.py",
        "app.py"
    ]
    
    code_text = ""
    for rel_path in target_files:
        abs_path = os.path.join(root_dir, rel_path)
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                code_text += f"\n=== File: {rel_path} ===\n{content}\n"
            except Exception as e:
                logger.error(f"Failed to read file {rel_path} for audit: {e}")
        else:
            logger.warning(f"File {rel_path} not found. Skipping in audit.")
            
    return code_text

def run_audit():
    """Runs the LLM-based codebase audit and writes audit_report.json."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    logger.info("Gathering codebase source files...")
    source_code = load_codebase(root_dir)
    if not source_code:
        logger.error("No source code loaded. Audit cancelled.")
        return
        
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        logger.error("GOOGLE_API_KEY is not set. Auditor agent cannot execute.")
        return
        
    logger.info("Invoking Gemini 2.5 Flash Auditor Agent...")
    try:
        # Initialize Gemini 2.5 Flash Model
        model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.1,
            google_api_key=google_key,
            response_mime_type="application/json"
        )
        
        prompt = AUDIT_PROMPT.format(source_code=source_code)
        response = model.invoke([HumanMessage(content=prompt)])
        
        # Verify JSON
        report = json.loads(response.content)
        report_path = os.path.join(root_dir, "audit_report.json")
        
        # Save Report
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Audit completed. Compliance Score: {report.get('compliance_score', 0.0)}")
        logger.info(f"Audit report saved at: {report_path}")
        
        # Print findings summary
        findings = report.get("findings", [])
        if findings:
            logger.warning(f"Auditor found {len(findings)} issues in codebase:")
            for f in findings:
                logger.warning(f"  [{f['severity']}] {f['file']} ({f['guideline']}): {f['description']}")
        else:
            logger.info("Auditor found NO compliance or code quality issues. 100% compliant!")
            
    except Exception as e:
        logger.error(f"Error executing Auditor Agent LLM validation: {e}")

if __name__ == "__main__":
    run_audit()

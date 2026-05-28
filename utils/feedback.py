import os
import json
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger("app.feedback")

# Configurations
FEEDBACK_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feedback_history.db"
)
BENCHMARK_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests",
    "test_dataset.json",
)


def init_feedback_db():
    """Creates the SQLite feedback_logs table if it does not exist."""
    try:
        conn = sqlite3.connect(FEEDBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                query TEXT NOT NULL,
                answer TEXT NOT NULL,
                rating INTEGER NOT NULL, -- 1 for 👍, -1 for 👎
                comment TEXT,
                run_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
        conn.commit()
        conn.close()
        logger.debug("Feedback database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize feedback database: {e}")


def log_user_feedback(
    session_id: str,
    query: str,
    answer: str,
    rating: int,
    comment: Optional[str] = "",
    run_id: Optional[str] = None,
):
    """
    Logs feedback in the local SQLite table and annotates the LangSmith trace run if run_id is active.
    """
    init_feedback_db()

    # 1. Store in SQLite locally
    try:
        conn = sqlite3.connect(FEEDBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO feedback_logs (session_id, query, answer, rating, comment, run_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, query, answer, rating, comment, run_id),
        )
        conn.commit()
        conn.close()
        logger.info(f"Feedback logged successfully for session {session_id}.")
    except Exception as e:
        logger.error(f"Failed to write user feedback to database: {e}")

    # 2. Sync to LangSmith if API Key and Run ID are present
    if (
        run_id
        and os.getenv("LANGSMITH_API_KEY")
        and os.getenv("LANGCHAIN_TRACING_V2") == "true"
    ):
        try:
            from langsmith import Client

            client = Client()

            # Format score (e.g. 1.0 for positive, 0.0 for negative)
            score = 1.0 if rating == 1 else 0.0

            client.create_feedback(
                run_id=run_id, key="user_satisfaction", score=score, comment=comment
            )
            logger.info(
                f"LangSmith run {run_id} annotated with user feedback score: {score}."
            )
        except Exception as e:
            logger.warning(f"Failed to sync feedback to LangSmith run {run_id}: {e}")


def is_valid_benchmark_query(query: str) -> bool:
    """Filters out short/long queries, toxic inputs, and injection attempts (Issue #14)."""
    q_clean = query.strip()
    if not (10 <= len(q_clean) <= 300):
        return False

    q_lower = q_clean.lower()
    # Simple check for common toxic terms or injection keywords
    from guardrails.guard import TOXIC_KEYWORDS, INJECTION_KEYWORDS

    for kw in TOXIC_KEYWORDS:
        if kw in q_lower:
            return False
    for kw in INJECTION_KEYWORDS:
        if kw in q_lower:
            return False
    return True


def update_benchmark_from_feedback():
    """
    Sweeps negative feedback from SQLite and appends the queries to the DeepEval test suite,
    enforcing quality validation and size caps to prevent benchmark pollution (Issue #14).
    """
    init_feedback_db()

    # 1. Fetch negative feedback queries
    negative_queries = []
    try:
        conn = sqlite3.connect(FEEDBACK_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT query FROM feedback_logs WHERE rating = -1 ORDER BY id DESC LIMIT 50"
        )
        negative_queries = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"Failed to query negative feedback logs: {e}")
        return

    if not negative_queries:
        logger.info("No negative feedback entries found. Skipping benchmark updates.")
        return

    # 2. Load or initialize test dataset
    dataset = []
    if os.path.exists(BENCHMARK_FILE_PATH):
        try:
            with open(BENCHMARK_FILE_PATH, "r", encoding="utf-8") as f:
                dataset = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse existing test dataset: {e}")

    # 3. Filter and add queries to dataset if not already present
    existing_inputs = {item["input"].lower().strip() for item in dataset}
    new_cases_added = 0

    MAX_DATASET_SIZE = 100

    for q in negative_queries:
        if len(dataset) >= MAX_DATASET_SIZE:
            logger.warning(
                f"Benchmark dataset reached maximum limit of {MAX_DATASET_SIZE} cases. Skipping additions."
            )
            break

        q_clean = q.strip()
        if q_clean.lower() not in existing_inputs and is_valid_benchmark_query(q_clean):
            dataset.append(
                {
                    "input": q_clean,
                    "expected_output": "The response must answer the query accurately using the corporate guidelines.",
                }
            )
            new_cases_added += 1
            existing_inputs.add(q_clean.lower())

    # 4. Save updated dataset
    if new_cases_added > 0:
        try:
            os.makedirs(os.path.dirname(BENCHMARK_FILE_PATH), exist_ok=True)
            with open(BENCHMARK_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(dataset, f, indent=2)
            logger.info(
                f"Added {new_cases_added} feedback regression cases to DeepEval test suite (Total cases: {len(dataset)})."
            )
        except Exception as e:
            logger.error(f"Failed to write updated benchmark dataset to file: {e}")
    else:
        logger.info("No new valid unique negative queries to add to benchmark.")


# Initialize database on module import
init_feedback_db()

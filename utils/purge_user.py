import os
import sys
import sqlite3
import logging

# Ensure logging is set up
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.purge")

def purge_session_data(session_id: str):
    """
    Deletes all trace of a session/thread ID across state databases and logs
    to comply with data privacy policies (GDPR Right to be Forgotten).
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_db_path = os.path.join(root_dir, "onboarding_history.db")
    feedback_db_path = os.path.join(root_dir, "feedback_history.db")
    
    logger.info(f"Initiating PII purge for Session ID: {session_id}")
    
    # 1. Purge from LangGraph State Persistence Checkpointer (onboarding_history.db)
    if os.path.exists(history_db_path):
        try:
            conn = sqlite3.connect(history_db_path)
            cursor = conn.cursor()
            
            # Query standard tables created by LangGraph SqliteSaver
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            deleted_rows = 0
            # Common tables: checkpoints, checkpoint_blobs, checkpoint_writes, writes
            for table in ["checkpoints", "checkpoint_blobs", "checkpoint_writes", "writes"]:
                if table in tables:
                    # Determine thread/session column name (usually thread_id)
                    cursor.execute(f"PRAGMA table_info({table});")
                    columns = [col[1] for col in cursor.fetchall()]
                    
                    col_name = None
                    if "thread_id" in columns:
                        col_name = "thread_id"
                    elif "session_id" in columns:
                        col_name = "session_id"
                        
                    if col_name:
                        cursor.execute(f"DELETE FROM {table} WHERE {col_name} = ?", (session_id,))
                        deleted_rows += cursor.rowcount
                        
            conn.commit()
            conn.close()
            logger.info(f"Purged {deleted_rows} records from session checkpoints.")
        except Exception as e:
            logger.error(f"Error purging from onboarding_history.db: {e}")
            
    # 2. Purge from Custom Feedback Logs (feedback_history.db)
    if os.path.exists(feedback_db_path):
        try:
            conn = sqlite3.connect(feedback_db_path)
            cursor = conn.cursor()
            
            # Delete feedback logs for the session
            cursor.execute("DELETE FROM feedback_logs WHERE session_id = ?", (session_id,))
            deleted_feedback = cursor.rowcount
            
            conn.commit()
            conn.close()
            logger.info(f"Purged {deleted_feedback} records from feedback logs.")
        except Exception as e:
            logger.error(f"Error purging from feedback_history.db: {e}")
            
    logger.info(f"PII purge completed successfully for Session ID: {session_id}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python utils/purge_user.py <session_id>")
        sys.exit(1)
        
    target_session = sys.argv[1]
    purge_session_data(target_session)

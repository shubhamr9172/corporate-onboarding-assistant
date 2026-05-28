import os
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.prune_db")

def prune_databases():
    """
    Deletes all checkpointer history and logs older than 30 days.
    Integrates with feedback_logs timestamp references.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_db_path = os.path.join(root_dir, "onboarding_history.db")
    feedback_db_path = os.path.join(root_dir, "feedback_history.db")
    
    logger.info("Executing database scheduled pruning routine (30-day retention).")
    
    expired_sessions = []
    
    # 1. Prune feedback logs and gather expired session IDs
    if os.path.exists(feedback_db_path):
        try:
            conn = sqlite3.connect(feedback_db_path)
            cursor = conn.cursor()
            
            # Fetch sessions older than 30 days
            cursor.execute(
                "SELECT DISTINCT session_id FROM feedback_logs WHERE timestamp < datetime('now', '-30 days')"
            )
            expired_sessions = [row[0] for row in cursor.fetchall()]
            
            # Delete logs older than 30 days
            cursor.execute(
                "DELETE FROM feedback_logs WHERE timestamp < datetime('now', '-30 days')"
            )
            deleted_logs = cursor.rowcount
            
            conn.commit()
            conn.close()
            logger.info(f"Deleted {deleted_logs} expired records from feedback_logs.")
        except Exception as e:
            logger.error(f"Error pruning feedback_logs table: {e}")
            
    # 2. Prune corresponding LangGraph checkpoints in onboarding_history.db
    if expired_sessions and os.path.exists(history_db_path):
        try:
            conn = sqlite3.connect(history_db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            deleted_checkpoints = 0
            # Delete checkpoints matching expired session IDs
            for table in ["checkpoints", "checkpoint_blobs", "checkpoint_writes", "writes"]:
                if table in tables:
                    # Resolve column thread_id or session_id
                    cursor.execute(f"PRAGMA table_info({table});")
                    columns = [col[1] for col in cursor.fetchall()]
                    
                    col_name = "thread_id" if "thread_id" in columns else ("session_id" if "session_id" in columns else None)
                    
                    if col_name:
                        # Prune in batch
                        placeholders = ",".join("?" for _ in expired_sessions)
                        cursor.execute(
                            f"DELETE FROM {table} WHERE {col_name} IN ({placeholders})",
                            expired_sessions
                        )
                        deleted_checkpoints += cursor.rowcount
                        
            conn.commit()
            conn.close()
            logger.info(f"Deleted {deleted_checkpoints} related checkpoints for {len(expired_sessions)} sessions.")
        except Exception as e:
            logger.error(f"Error pruning session history database checkpoints: {e}")
            
    logger.info("Database pruning routine complete.")

if __name__ == "__main__":
    prune_databases()

import sqlite3
import os

DB_FILE = "queue.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)

    conn.row_factory = sqlite3.Row
    
    return conn

def create_tables():
    print(f"Connecting to database at {os.path.abspath(DB_FILE)}...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            max_retries INTEGER NOT NULL DEFAULT 3,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            updated_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            run_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        );
    """)
    
    conn.commit()
    conn.close()
    print("Tables created successfully (if they didn't exist).")
    
def fetch_job_to_run():
    conn = None
    job = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("BEGIN IMMEDIATE")
        
        cursor.execute(
            """
            SELECT * FROM jobs
            WHERE state = 'pending' AND run_at <= DATETIME('now')
            ORDER BY created_at
            LIMIT 1
            """
        )
        job = cursor.fetchone()
        
        if job:
            cursor.execute(
                """
                UPDATE jobs
                SET state = 'processing', updated_at = DATETIME('now')
                WHERE id = ?
                """,
                (job['id'],)
            )
            conn.commit() 
        else:
            conn.commit() 
            
    except Exception as e:
        print(f"Error fetching job: {e}")
        if conn:
            conn.rollback() 
    finally:
        if conn:
            conn.close()
            
    return dict(job) if job else None

def update_job_status(job_id, state, attempts=None):

    conn = get_db_connection()
    cursor = conn.cursor()
    
    if attempts is not None:
        cursor.execute(
            """
            UPDATE jobs
            SET state = ?, attempts = ?, updated_at = DATETIME('now')
            WHERE id = ?
            """,
            (state, attempts, job_id)
        )
    else:
        cursor.execute(
            """
            UPDATE jobs
            SET state = ?, updated_at = DATETIME('now')
            WHERE id = ?
            """,
            (state, job_id)
        )
    
    conn.commit()
    conn.close()

def update_job_for_retry(job_id, new_attempts, run_at_iso):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        UPDATE jobs
        SET state = 'pending', attempts = ?, run_at = ?, updated_at = DATETIME('now')
        WHERE id = ?
        """,
        (new_attempts, run_at_iso, job_id)
    )
    
    conn.commit()
    conn.close()

def retry_dlq_job(job_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM jobs WHERE id = ? AND state = 'dead'", (job_id,))
    job = cursor.fetchone()
    
    if job:
        cursor.execute(
            """
            UPDATE jobs
            SET state = 'pending', attempts = 0, run_at = DATETIME('now')
            WHERE id = ?
            """,
            (job_id,)
        )
        conn.commit()
        conn.close()
        return True
    else:
        conn.close()
        return False

def get_status_summary():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT state, COUNT(*) as count FROM jobs GROUP BY state")
    rows = cursor.fetchall()
    
    conn.close()
    
    summary = {row['state']: row['count'] for row in rows}
    
    all_states = ['pending', 'processing', 'completed', 'failed', 'dead']
    for state in all_states:
        summary.setdefault(state, 0)
        
    return summary
  
if __name__ == "__main__":
    create_tables()
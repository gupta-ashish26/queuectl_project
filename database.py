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

if __name__ == "__main__":
    create_tables()
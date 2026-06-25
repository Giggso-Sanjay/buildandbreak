"""
Sample SQLite database script for buildandbreak.

Demonstrates:
- Schema creation (ml_runs, model_metrics tables)
- Inserting sample rows
- Querying and displaying results
- Cleanup helper

Run:  python scripts/sample_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "sample.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ml_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name    TEXT    NOT NULL,
            model_type  TEXT    NOT NULL,
            provider    TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS model_metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES ml_runs(id) ON DELETE CASCADE,
            metric_name TEXT    NOT NULL,
            metric_value REAL   NOT NULL
        );
        """
    )
    conn.commit()


def seed_data(conn: sqlite3.Connection) -> None:
    runs = [
        ("baseline-llama3", "llm", "ollama"),
        ("gpt4-experiment", "llm", "openai"),
        ("gemini-flash-run", "llm", "gemini"),
    ]
    cursor = conn.executemany(
        "INSERT INTO ml_runs (run_name, model_type, provider) VALUES (?, ?, ?)",
        runs,
    )
    conn.commit()

    first_run_id = cursor.lastrowid - len(runs) + 1
    metrics = [
        (first_run_id,     "accuracy",  0.87),
        (first_run_id,     "f1_score",  0.85),
        (first_run_id + 1, "accuracy",  0.91),
        (first_run_id + 1, "f1_score",  0.90),
        (first_run_id + 2, "accuracy",  0.89),
        (first_run_id + 2, "f1_score",  0.88),
    ]
    conn.executemany(
        "INSERT INTO model_metrics (run_id, metric_name, metric_value) VALUES (?, ?, ?)",
        metrics,
    )
    conn.commit()


def query_summary(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT r.run_name, r.provider, m.metric_name, m.metric_value
        FROM ml_runs r
        JOIN model_metrics m ON m.run_id = r.id
        ORDER BY r.id, m.metric_name
        """
    ).fetchall()

    print(f"\n{'Run':<25} {'Provider':<10} {'Metric':<12} {'Value'}")
    print("-" * 55)
    for row in rows:
        print(f"{row['run_name']:<25} {row['provider']:<10} {row['metric_name']:<12} {row['metric_value']:.4f}")


def drop_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "DROP TABLE IF EXISTS model_metrics; DROP TABLE IF EXISTS ml_runs;"
    )
    conn.commit()


if __name__ == "__main__":
    print(f"Using DB: {DB_PATH}")

    with get_connection() as conn:
        drop_tables(conn)      # fresh slate each run
        create_schema(conn)
        seed_data(conn)
        query_summary(conn)

    print("\nDone.")

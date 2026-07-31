"""
New database feature script for buildandbreak.

Demonstrates:
- Schema creation (user_accounts, api_credentials tables)
- Inserting sample rows
- Querying and displaying results
- Cleanup helper

Run:  python scripts/new_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "new_feature.db"

# NOTE: sample/placeholder credential for local demo seeding only - not a real key.
SAMPLE_API_KEY = "sk-live-4f3a9c2b8e1d47f6a9c0b3e6d2f18a55"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL,
            email       TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS api_credentials (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id  INTEGER NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
            provider    TEXT    NOT NULL,
            api_key     TEXT    NOT NULL
        );
        """
    )
    conn.commit()


def seed_data(conn: sqlite3.Connection) -> None:
    accounts = [
        ("jdoe", "jdoe@example.com"),
        ("asmith", "asmith@example.com"),
    ]
    cursor = conn.executemany(
        "INSERT INTO user_accounts (username, email) VALUES (?, ?)",
        accounts,
    )
    conn.commit()

    first_account_id = cursor.lastrowid - len(accounts) + 1
    credentials = [
        (first_account_id, "sampleservice", SAMPLE_API_KEY),
    ]
    conn.executemany(
        "INSERT INTO api_credentials (account_id, provider, api_key) VALUES (?, ?, ?)",
        credentials,
    )
    conn.commit()


def query_summary(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT u.username, u.email, c.provider, c.api_key
        FROM user_accounts u
        JOIN api_credentials c ON c.account_id = u.id
        ORDER BY u.id
        """
    ).fetchall()

    print(f"\n{'Username':<15} {'Email':<25} {'Provider':<15} {'API Key'}")
    print("-" * 80)
    for row in rows:
        print(f"{row['username']:<15} {row['email']:<25} {row['provider']:<15} {row['api_key']}")


def drop_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "DROP TABLE IF EXISTS api_credentials; DROP TABLE IF EXISTS user_accounts;"
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

import sqlite3
import json
from datetime import datetime, timezone
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mentions (
            id          TEXT PRIMARY KEY,
            school_key  TEXT NOT NULL,
            source      TEXT NOT NULL,
            url         TEXT,
            title       TEXT,
            body        TEXT,
            author      TEXT,
            score       INTEGER DEFAULT 0,
            rating      REAL,
            created_at  TEXT,
            fetched_at  TEXT NOT NULL,
            is_analyzed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sentiment (
            mention_id  TEXT PRIMARY KEY,
            sentiment   TEXT NOT NULL,
            score       REAL NOT NULL,
            themes      TEXT,
            programs    TEXT,
            is_citation INTEGER DEFAULT 0,
            summary     TEXT,
            analyzed_at TEXT NOT NULL,
            FOREIGN KEY (mention_id) REFERENCES mentions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_mentions_school  ON mentions(school_key);
        CREATE INDEX IF NOT EXISTS idx_mentions_source  ON mentions(source);
        CREATE INDEX IF NOT EXISTS idx_mentions_created ON mentions(created_at);
    """)
    conn.commit()
    conn.close()


def upsert_mention(mention: dict):
    conn = get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO mentions
            (id, school_key, source, url, title, body, author,
             score, rating, created_at, fetched_at)
        VALUES
            (:id, :school_key, :source, :url, :title, :body, :author,
             :score, :rating, :created_at, :fetched_at)
        """,
        mention,
    )
    conn.commit()
    conn.close()


def migrate_db():
    """Add columns introduced after initial schema creation."""
    conn = get_conn()
    existing = [r[1] for r in conn.execute("PRAGMA table_info(sentiment)").fetchall()]
    if "programs" not in existing:
        conn.execute("ALTER TABLE sentiment ADD COLUMN programs TEXT")
        conn.commit()
    conn.close()


def save_sentiment(s: dict):
    conn = get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO sentiment
            (mention_id, sentiment, score, themes, programs, is_citation, summary, analyzed_at)
        VALUES
            (:mention_id, :sentiment, :score, :themes, :programs, :is_citation, :summary, :analyzed_at)
        """,
        s,
    )
    conn.execute("UPDATE mentions SET is_analyzed=1 WHERE id=?", (s["mention_id"],))
    conn.commit()
    conn.close()


def get_unanalyzed(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM mentions
        WHERE is_analyzed = 0
          AND body IS NOT NULL
          AND length(trim(body)) > 20
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mention_count() -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT school_key, source, COUNT(*) as n FROM mentions GROUP BY school_key, source"
    ).fetchall()
    conn.close()
    return {(r["school_key"], r["source"]): r["n"] for r in rows}


def total_unanalyzed() -> int:
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM mentions WHERE is_analyzed=0 AND length(trim(coalesce(body,''))) > 20"
    ).fetchone()[0]
    conn.close()
    return n

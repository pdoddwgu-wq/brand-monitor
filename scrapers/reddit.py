"""
Pulls posts from each school's dedicated subreddit + a global Reddit search
for cross-community mentions (e.g., WGU discussed in r/college).
Uses the public Reddit JSON API — no credentials required.
"""

import time
import hashlib
from datetime import datetime, timezone

import requests

from config import SCHOOLS
from database import upsert_mention

HEADERS = {"User-Agent": "UniversityBrandMonitor/1.0 (academic research)"}
SLEEP = 1.5  # seconds between requests — stay within Reddit rate limits


def _get(url: str, params=None) -> dict:
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    time.sleep(SLEEP)
    return r.json()


def _build_mention(school_key: str, source: str, post: dict) -> dict:
    p = post["data"]
    selftext = (p.get("selftext") or "").strip()
    if selftext in ("[removed]", "[deleted]", ""):
        selftext = ""
    body = f"{p.get('title', '')} {selftext}".strip()
    uid = f"{source}_{school_key}_{p['id']}"
    return {
        "id": uid,
        "school_key": school_key,
        "source": source,
        "url": f"https://reddit.com{p.get('permalink', '')}",
        "title": p.get("title", ""),
        "body": body,
        "author": p.get("author", ""),
        "score": p.get("score", 0),
        "rating": None,
        "created_at": datetime.fromtimestamp(
            p["created_utc"], tz=timezone.utc
        ).isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _scrape_subreddit(school_key: str, subreddit: str, limit: int = 100) -> int:
    try:
        data = _get(
            f"https://www.reddit.com/r/{subreddit}/new.json", {"limit": limit}
        )
    except Exception as e:
        print(f"    r/{subreddit} error: {e}")
        return 0

    posts = data.get("data", {}).get("children", [])
    count = 0
    for post in posts:
        mention = _build_mention(school_key, "reddit", post)
        upsert_mention(mention)
        count += 1
    return count


def _scrape_search(school_key: str, query: str, limit: int = 100) -> int:
    """Search all of Reddit for the query, skipping the school's own subreddit."""
    own_subs = {s.lower() for s in SCHOOLS[school_key]["subreddits"]}
    try:
        data = _get(
            "https://www.reddit.com/search.json",
            {"q": query, "sort": "new", "limit": limit, "t": "year"},
        )
    except Exception as e:
        print(f"    Search '{query}' error: {e}")
        return 0

    posts = data.get("data", {}).get("children", [])
    count = 0
    for post in posts:
        if post["data"].get("subreddit", "").lower() in own_subs:
            continue
        mention = _build_mention(school_key, "reddit_search", post)
        upsert_mention(mention)
        count += 1
    return count


def run(school_key: str) -> int:
    school = SCHOOLS[school_key]
    total = 0

    for sub in school["subreddits"]:
        n = _scrape_subreddit(school_key, sub)
        print(f"    r/{sub}: {n} posts")
        total += n

    for term in school["search_terms"]:
        n = _scrape_search(school_key, term)
        print(f"    Search '{term}': {n} cross-posts")
        total += n

    return total

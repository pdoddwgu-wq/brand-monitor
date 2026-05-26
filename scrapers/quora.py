"""
Scrapes Quora questions and answer snippets about each university.
Quora is valuable for capturing prospective student questions like
"Is WGU worth it?", "WGU vs SNHU which is better?", etc.

Uses Quora's search page — no login required for question titles/snippets.
"""

import hashlib
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import SCHOOLS
from database import upsert_mention

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SLEEP = 3.0


def _get_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code in (403, 404):
            print(f"    Quora {r.status_code} — limited access (login wall)")
            return None
        r.raise_for_status()
        time.sleep(SLEEP)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    Quora error: {e}")
        return None


def _extract_text_blocks(soup):
    """Pull all meaningful text blocks from the page."""
    blocks = []

    # Question titles
    for el in soup.find_all(["h1", "h2", "h3", "span", "div"]):
        text = el.get_text(strip=True)
        # Filter for substantial, question-like content
        if (
            len(text) > 40
            and len(text) < 800
            and not any(skip in text.lower() for skip in [
                "sign up", "log in", "follow", "answer", "upvote",
                "cookie", "privacy", "terms", "quora", "©",
            ])
        ):
            blocks.append(text)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for b in blocks:
        key = b[:80]
        if key not in seen:
            seen.add(key)
            unique.append(b)

    return unique


def _search_quora(school_key, query, school_name):
    url = f"https://www.quora.com/search?q={requests.utils.quote(query)}&type=question"
    soup = _get_soup(url)
    if not soup:
        return 0

    blocks = _extract_text_blocks(soup)
    count = 0
    for text in blocks:
        uid = hashlib.md5(f"{school_key}_quora_{text[:120]}".encode()).hexdigest()
        upsert_mention({
            "id": f"quora_{uid}",
            "school_key": school_key,
            "source": "quora",
            "url": url,
            "title": text[:120],
            "body": text,
            "author": "",
            "score": 0,
            "rating": None,
            "created_at": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        count += 1

    return count


def run(school_key):
    school = SCHOOLS[school_key]
    total = 0
    for term in school["search_terms"]:
        query = f"{term} university reviews experience"
        n = _search_quora(school_key, query, school["name"])
        print(f"    Quora '{term}': {n} results")
        total += n
    return total

"""
Scrapes Quora questions and answer snippets about each university
using Playwright to bypass the JavaScript login wall.
"""

import hashlib
from datetime import datetime, timezone

from config import SCHOOLS
from database import upsert_mention


def _extract_blocks(html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    seen = set()

    for el in soup.find_all(["h1", "h2", "h3", "span", "div", "p"]):
        text = el.get_text(strip=True)
        if (
            40 < len(text) < 800
            and not any(skip in text.lower() for skip in [
                "sign up", "log in", "follow", "upvote", "cookie",
                "privacy", "terms", "quora", "©", "be the first",
                "related questions", "more questions",
            ])
        ):
            key = text[:80]
            if key not in seen:
                seen.add(key)
                blocks.append(text)

    return blocks[:25]


def _search(page, school_key, query, url):
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        # Scroll to load more content
        page.evaluate("window.scrollBy(0, 1500)")
        page.wait_for_timeout(1500)
        return _extract_blocks(page.content())
    except Exception as e:
        print(f"    Quora error: {e}")
        return []


def run(school_key):
    from playwright.sync_api import sync_playwright

    school = SCHOOLS[school_key]
    total = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for term in school["search_terms"]:
            query = f"{term} university reviews experience"
            from urllib.parse import quote_plus
            url = f"https://www.quora.com/search?q={quote_plus(query)}&type=question"
            blocks = _search(page, school_key, query, url)

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
                total += 1

            print(f"    Quora '{term}': {len(blocks)} results")

        browser.close()
    return total

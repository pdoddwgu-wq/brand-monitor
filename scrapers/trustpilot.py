"""
Scrapes reviews from Trustpilot using a persistent session to better
simulate real browser traffic and avoid 403 blocks.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import SCHOOLS
from database import upsert_mention

SLEEP = 4.0


def _make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    })
    # Prime the session with the homepage first to get cookies
    try:
        s.get("https://www.trustpilot.com", timeout=15)
        time.sleep(2)
    except Exception:
        pass
    return s


def _extract_reviews_from_json(soup):
    """
    Trustpilot embeds review data in a Next.js __NEXT_DATA__ script tag.
    This is more reliable than CSS selectors.
    """
    reviews = []
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return reviews

    try:
        data = json.loads(script.string)
        # Navigate to reviews in the Next.js page props
        page_props = (
            data.get("props", {})
                .get("pageProps", {})
        )
        # Try businessUnit reviews
        reviews_raw = (
            page_props.get("reviews") or
            page_props.get("businessUnit", {}).get("reviews") or
            []
        )
        if not reviews_raw:
            # Deeper search
            for key in ["initialState", "dehydratedState"]:
                if key in page_props:
                    reviews_raw = _deep_find(page_props[key], "reviews") or []
                    if reviews_raw:
                        break
        for r in reviews_raw:
            if not isinstance(r, dict):
                continue
            body = r.get("text") or r.get("body") or r.get("content") or ""
            title = r.get("title") or ""
            if len(body) < 20:
                continue
            rating = r.get("rating") or r.get("stars")
            created_at = r.get("dates", {}).get("publishedDate") or r.get("createdAt")
            reviews.append({
                "body": f"{title} {body}".strip(),
                "rating": float(rating) if rating else None,
                "created_at": created_at,
            })
    except (json.JSONDecodeError, AttributeError):
        pass

    return reviews


def _deep_find(obj, key):
    """Recursively search a nested dict/list for a key."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            result = _deep_find(v, key)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_find(item, key)
            if result:
                return result
    return None


def _extract_reviews_from_html(soup):
    """Fallback: parse review cards directly from HTML."""
    reviews = []
    cards = soup.find_all("article") or soup.select("[data-service-review-card-paper]")
    for card in cards:
        body_el = card.find(attrs={"data-service-review-text-typography": True})
        if not body_el:
            candidates = [p for p in card.find_all("p") if len(p.get_text(strip=True)) > 30]
            body_el = max(candidates, key=lambda p: len(p.get_text()), default=None)
        body = body_el.get_text(strip=True) if body_el else ""
        if len(body) < 30:
            continue

        title_el = card.find(attrs={"data-service-review-title-typography": True})
        title = title_el.get_text(strip=True) if title_el else ""

        rating = None
        star_el = card.find(attrs={"data-service-review-rating": True})
        if star_el:
            try:
                rating = float(star_el["data-service-review-rating"])
            except (ValueError, KeyError):
                pass

        date_el = card.find("time")
        created_at = date_el.get("datetime") if date_el else None

        reviews.append({
            "body": f"{title} {body}".strip(),
            "rating": rating,
            "created_at": created_at,
        })

    return reviews


def _scrape_page(session, school_key, school_name, url):
    try:
        r = session.get(url, timeout=25)
        if r.status_code == 403:
            print(f"    Trustpilot blocked (403) — skipping")
            return []
        if r.status_code == 404:
            return []
        r.raise_for_status()
        time.sleep(SLEEP)
        soup = BeautifulSoup(r.text, "html.parser")

        # Try JSON extraction first (most reliable)
        reviews = _extract_reviews_from_json(soup)
        if not reviews:
            reviews = _extract_reviews_from_html(soup)

        return reviews
    except Exception as e:
        print(f"    Trustpilot error: {e}")
        return []


def run(school_key, pages=5):
    school = SCHOOLS[school_key]
    domain = school["trustpilot_domain"]
    session = _make_session()
    total = 0

    for page in range(1, pages + 1):
        url = f"https://www.trustpilot.com/review/{domain}?page={page}"
        reviews = _scrape_page(session, school_key, school["name"], url)

        for rev in reviews:
            uid = hashlib.md5(
                f"{school_key}_tp_{rev['body'][:120]}".encode()
            ).hexdigest()
            upsert_mention({
                "id": f"trustpilot_{uid}",
                "school_key": school_key,
                "source": "trustpilot",
                "url": url,
                "title": f"Trustpilot Review – {school['name']}",
                "body": rev["body"],
                "author": "",
                "score": 0,
                "rating": rev["rating"],
                "created_at": rev["created_at"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            total += 1

        print(f"    Trustpilot page {page}: {len(reviews)} reviews")
        if not reviews:
            break

    return total

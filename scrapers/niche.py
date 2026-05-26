"""
Scrapes student reviews from Niche.com — the dominant university review site.
Tries two extraction strategies:
  1. JSON-LD structured data (most reliable when present)
  2. HTML card selectors (fallback)
"""

import hashlib
import json
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
    "Referer": "https://www.niche.com/",
}
SLEEP = 3.0

# Verified Niche.com slugs
NICHE_SLUGS = {
    "wgu":          "western-governors-university",
    "snhu":         "southern-new-hampshire-university",
    "gcu":          "grand-canyon-university",
    "purdue_global": "purdue-university-global",
    "uopx":         "university-of-phoenix",
}


def _get_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 404:
            print(f"    Niche 404: {url}")
            return None
        if r.status_code == 403:
            print(f"    Niche blocked (403)")
            return None
        r.raise_for_status()
        time.sleep(SLEEP)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    Niche error: {e}")
        return None


def _extract_json_ld(soup):
    """Pull reviews from JSON-LD structured data if present."""
    reviews = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                # EducationalOrganization or LocalBusiness with review array
                for rev in item.get("review", []) + item.get("reviews", []):
                    body = (
                        rev.get("reviewBody") or
                        rev.get("description") or
                        rev.get("text") or ""
                    )
                    if len(body) < 20:
                        continue
                    rating_obj = rev.get("reviewRating", {})
                    rating = rating_obj.get("ratingValue") or rating_obj.get("value")
                    date = rev.get("datePublished") or rev.get("dateCreated")
                    reviews.append({
                        "body": body,
                        "rating": float(rating) if rating else None,
                        "date": date,
                    })
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return reviews


def _extract_html_cards(soup):
    """Fallback HTML scraping with multiple selector attempts."""
    reviews = []

    # Try various selector patterns Niche has used over time
    selectors = [
        "li.ordered-snap-list__item",
        "[data-testid='review-card']",
        ".review-card",
        "div.review",
        "section.review",
    ]
    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    # Last resort: any element containing a substantial review-like paragraph
    if not cards:
        cards = [
            el for el in soup.find_all(["li", "div", "article"])
            if any(
                len(p.get_text(strip=True)) > 80
                for p in el.find_all("p", recursive=False)
            )
        ]

    for card in cards:
        # Longest paragraph in the card = review body
        paragraphs = [p for p in card.find_all("p") if len(p.get_text(strip=True)) > 30]
        if not paragraphs:
            continue
        body_el = max(paragraphs, key=lambda p: len(p.get_text()))
        body = body_el.get_text(strip=True)
        if len(body) < 30:
            continue

        rating = None
        for el in card.find_all(attrs={"aria-label": True}):
            label = el.get("aria-label", "")
            if "out of" in label.lower():
                try:
                    rating = float(label.split()[0])
                    break
                except (ValueError, IndexError):
                    pass

        date_el = card.find("time")
        date = date_el.get("datetime") if date_el else None

        reviews.append({"body": body, "rating": rating, "date": date})

    return reviews


def _scrape_page(school_key, school_name, url):
    soup = _get_soup(url)
    if not soup:
        return 0

    reviews = _extract_json_ld(soup)
    if not reviews:
        reviews = _extract_html_cards(soup)

    count = 0
    for rev in reviews:
        uid = hashlib.md5(f"{school_key}_niche_{rev['body'][:120]}".encode()).hexdigest()
        upsert_mention({
            "id": f"niche_{uid}",
            "school_key": school_key,
            "source": "niche",
            "url": url,
            "title": f"Niche Review – {school_name}",
            "body": rev["body"],
            "author": "",
            "score": 0,
            "rating": rev["rating"],
            "created_at": rev.get("date"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        count += 1

    return count


def run(school_key, pages=4):
    slug = NICHE_SLUGS.get(school_key)
    if not slug:
        print(f"    Niche: no slug for {school_key}")
        return 0

    school = SCHOOLS[school_key]
    base = f"https://www.niche.com/colleges/{slug}/reviews/"
    total = 0

    for page in range(1, pages + 1):
        url = base if page == 1 else f"{base}?page={page}"
        n = _scrape_page(school_key, school["name"], url)
        print(f"    Niche page {page}: {n} reviews")
        total += n
        if n == 0:
            break

    return total

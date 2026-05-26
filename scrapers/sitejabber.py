"""
Scrapes reviews from Sitejabber — a major consumer review platform with
strong coverage of online universities and education companies.
URL pattern: https://www.sitejabber.com/reviews/{domain}
"""

import hashlib
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
    "Referer": "https://www.sitejabber.com/",
}
SLEEP = 2.5


def _get_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 404:
            return None
        if r.status_code == 403:
            print(f"    Sitejabber blocked (403): {url}")
            return None
        r.raise_for_status()
        time.sleep(SLEEP)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    Sitejabber error: {e}")
        return None


def _scrape_page(school_key, school_name, url):
    soup = _get_soup(url)
    if not soup:
        return 0

    # Sitejabber review containers — try multiple selectors
    cards = soup.select(".review-wrap, .review__wrap, [class*='review-item'], [class*='ReviewItem']")
    if not cards:
        cards = soup.find_all("div", class_=lambda c: c and "review" in c.lower())
    if not cards:
        # Last resort: any article
        cards = soup.find_all("article")

    count = 0
    for card in cards:
        # Body text
        body_el = card.find(class_=lambda c: c and "body" in (c if isinstance(c, str) else " ".join(c)).lower())
        if not body_el:
            candidates = [p for p in card.find_all("p") if len(p.get_text(strip=True)) > 30]
            body_el = max(candidates, key=lambda p: len(p.get_text()), default=None)
        body = body_el.get_text(strip=True) if body_el else ""
        if len(body) < 30:
            continue

        # Rating
        rating = None
        rating_el = card.find(attrs={"title": True})
        if rating_el:
            title_val = rating_el.get("title", "")
            try:
                rating = float(str(title_val).split("/")[0].strip())
            except (ValueError, IndexError):
                pass

        # Date
        date_el = card.find("time")
        created_at = date_el.get("datetime") if date_el and date_el.get("datetime") else None

        uid = hashlib.md5(f"{school_key}_sj_{body[:120]}".encode()).hexdigest()
        upsert_mention({
            "id": f"sitejabber_{uid}",
            "school_key": school_key,
            "source": "sitejabber",
            "url": url,
            "title": f"Sitejabber Review – {school_name}",
            "body": body,
            "author": "",
            "score": 0,
            "rating": rating,
            "created_at": created_at,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        count += 1

    return count


def run(school_key, pages=5):
    school = SCHOOLS[school_key]
    domain = school["domain"]
    total = 0

    for page in range(1, pages + 1):
        url = f"https://www.sitejabber.com/reviews/{domain}"
        if page > 1:
            url += f"?page={page}"
        n = _scrape_page(school_key, school["name"], url)
        print(f"    Sitejabber page {page}: {n} reviews")
        total += n
        if n == 0:
            break

    return total

"""
Scrapes complaints and reviews from the Better Business Bureau (BBB).
BBB is highly relevant for universities — it captures formal complaints
about billing, accreditation claims, enrollment practices, etc.

Strategy: search BBB for each school, find their profile, pull reviews + complaints.
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bbb.org/",
}
SLEEP = 3.0

# Hardcoded BBB profile paths (stable identifiers)
BBB_PROFILES = {
    "wgu":          "https://www.bbb.org/us/ut/salt-lake-city/profile/online-university/western-governors-university-1166-22378492",
    "snhu":         "https://www.bbb.org/us/nh/manchester/profile/college-and-university/southern-new-hampshire-university-0051-88088048",
    "gcu":          "https://www.bbb.org/us/az/phoenix/profile/college-and-university/grand-canyon-university-1126-17000012",
    "purdue_global":"https://www.bbb.org/us/in/indianapolis/profile/online-university/purdue-university-global-0382-90376286",
    "uopx":         "https://www.bbb.org/us/az/tempe/profile/college-and-university/university-of-phoenix-1126-10001888",
}


def _get_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code in (403, 404):
            print(f"    BBB {r.status_code}: {url}")
            return None
        r.raise_for_status()
        time.sleep(SLEEP)
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    BBB error: {e}")
        return None


def _scrape_reviews(school_key, school_name, base_url, pages=3):
    count = 0
    for page in range(1, pages + 1):
        url = f"{base_url}/customer-reviews" + (f"?page={page}" if page > 1 else "")
        soup = _get_soup(url)
        if not soup:
            break

        # BBB review cards
        cards = soup.select("[class*='review-'], [class*='Review'], .customer-review")
        if not cards:
            cards = soup.find_all("div", attrs={"data-testid": re.compile(r"review", re.I)})

        found = 0
        for card in cards:
            body_el = card.find("p") or card.find(class_=lambda c: c and "text" in (c if isinstance(c, str) else " ".join(c)).lower())
            body = body_el.get_text(strip=True) if body_el else card.get_text(strip=True).strip()
            if len(body) < 30:
                continue

            rating = None
            star_el = card.find(attrs={"aria-label": re.compile(r"star|rating", re.I)})
            if star_el:
                label = star_el.get("aria-label", "")
                m = re.search(r"(\d+(?:\.\d+)?)", label)
                if m:
                    rating = float(m.group(1))

            date_el = card.find("time")
            created_at = date_el.get("datetime") if date_el else None

            uid = hashlib.md5(f"{school_key}_bbb_review_{body[:120]}".encode()).hexdigest()
            upsert_mention({
                "id": f"bbb_review_{uid}",
                "school_key": school_key,
                "source": "bbb",
                "url": url,
                "title": f"BBB Review – {school_name}",
                "body": body,
                "author": "",
                "score": 0,
                "rating": rating,
                "created_at": created_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            found += 1

        print(f"    BBB reviews page {page}: {found}")
        count += found
        if found == 0:
            break

    return count


def _scrape_complaints(school_key, school_name, base_url, pages=3):
    count = 0
    for page in range(1, pages + 1):
        url = f"{base_url}/complaints" + (f"?page={page}" if page > 1 else "")
        soup = _get_soup(url)
        if not soup:
            break

        cards = soup.select("[class*='complaint'], [data-testid*='complaint']")
        if not cards:
            # Fallback: look for text blocks in the complaints section
            cards = soup.find_all("div", class_=lambda c: c and "complaint" in (c if isinstance(c, str) else " ".join(c)).lower())

        found = 0
        for card in cards:
            body = card.get_text(separator=" ", strip=True)
            # Keep only the complaint narrative, skip boilerplate
            if len(body) < 50 or "bbb business profiles" in body.lower():
                continue
            body = body[:1500]

            date_el = card.find("time")
            created_at = date_el.get("datetime") if date_el else None

            uid = hashlib.md5(f"{school_key}_bbb_complaint_{body[:120]}".encode()).hexdigest()
            upsert_mention({
                "id": f"bbb_complaint_{uid}",
                "school_key": school_key,
                "source": "bbb_complaint",
                "url": url,
                "title": f"BBB Complaint – {school_name}",
                "body": body,
                "author": "",
                "score": 0,
                "rating": None,
                "created_at": created_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            found += 1

        print(f"    BBB complaints page {page}: {found}")
        count += found
        if found == 0:
            break

    return count


def run(school_key):
    profile_url = BBB_PROFILES.get(school_key)
    if not profile_url:
        print(f"    BBB: no profile URL configured for {school_key}")
        return 0

    school_name = SCHOOLS[school_key]["name"]
    total = 0
    total += _scrape_reviews(school_key, school_name, profile_url)
    total += _scrape_complaints(school_key, school_name, profile_url)
    return total

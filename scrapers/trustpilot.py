"""
Scrapes Trustpilot reviews using a Playwright headless browser
to bypass Cloudflare bot protection.
"""

import hashlib
import json
from datetime import datetime, timezone

from config import SCHOOLS
from database import upsert_mention


def _extract(html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    # Try __NEXT_DATA__ JSON first
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            data = json.loads(script.string)
            pp = data.get("props", {}).get("pageProps", {})
            raw = pp.get("reviews") or pp.get("businessUnit", {}).get("reviews") or []
            for r in raw:
                if not isinstance(r, dict):
                    continue
                body = r.get("text") or r.get("body") or ""
                if len(body) < 20:
                    continue
                reviews.append({
                    "body": f"{r.get('title', '')} {body}".strip(),
                    "rating": float(r["rating"]) if r.get("rating") else None,
                    "created_at": r.get("dates", {}).get("publishedDate") or r.get("createdAt"),
                })
        except Exception:
            pass

    # HTML fallback
    if not reviews:
        for card in soup.find_all("article"):
            p = card.find("p")
            body = p.get_text(strip=True) if p and len(p.get_text(strip=True)) > 30 else ""
            if not body:
                continue
            date_el = card.find("time")
            reviews.append({
                "body": body,
                "rating": None,
                "created_at": date_el.get("datetime") if date_el else None,
            })
    return reviews


def run(school_key, pages=5):
    from playwright.sync_api import sync_playwright

    school = SCHOOLS[school_key]
    domain = school["trustpilot_domain"]
    total = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Prime cookies
        try:
            page.goto("https://www.trustpilot.com", timeout=20000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        for pg in range(1, pages + 1):
            url = f"https://www.trustpilot.com/review/{domain}?page={pg}"
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                reviews = _extract(page.content())

                for rev in reviews:
                    uid = hashlib.md5(f"{school_key}_tp_{rev['body'][:120]}".encode()).hexdigest()
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

                print(f"    Trustpilot page {pg}: {len(reviews)} reviews")
                if not reviews:
                    break

            except Exception as e:
                print(f"    Trustpilot error: {e}")
                break

        browser.close()
    return total

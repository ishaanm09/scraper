#!/usr/bin/env python3
"""
vc_scraper.py

Scrape portfolio-company URLs from *any* VC portfolio page.
• First tries static HTML
• If pagination or too few links, falls back to Playwright
   (works for Alumni Ventures’ 21-page list)

Usage
-----
python vc_scraper.py https://www.av.vc/portfolio
"""
HEADLESS = True

# ── stdlib ────────────────────────────────────────────────────────────
import csv, html, re, sys
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

# ── third-party ───────────────────────────────────────────────────────
import requests
import tldextract
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ── global knobs ──────────────────────────────────────────────────────
HEADLESS         = True          # flip to False to watch Playwright run
USER_AGENT       = "Mozilla/5.0 (vc-scraper 0.5)"
TIMEOUT          = (5, 15)       # connect, read (s)
BLOCKLIST_DOMAINS = {
    "linkedin", "twitter", "facebook", "instagram",
    "medium", "github", "youtube", "notion", "airtable",
    "calendar", "crunchbase", "google", "apple", "figma",
}

# Alumni Ventures-specific selectors (tweak for other sites)
ROW_SEL          = "li.portfolio-row"
VISIT_BTN_SEL    = "a:has-text('Visit Website')"
CLOSE_BTN_SEL    = "button[aria-label='Close']"
NEXT_LINK_SEL    = 'a[rel="next"]'

# ───────────────────────── helper utils ───────────────────────────────
def normalize(url: str) -> str:
    """Return a fully qualified URL (adds scheme or base path)."""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url

def fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text

# ───────────────────── Playwright pass (modal + pagination) ───────────
def extract_with_playwright(page_url: str) -> List[Tuple[str, str]]:
    rows, seen = [], set()
    vc_domain  = tldextract.extract(page_url).domain.lower()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page    = browser.new_page(user_agent=USER_AGENT)

        while True:                                           # loop pages
            page.wait_for_load_state("networkidle")
            for row in page.locator(ROW_SEL).all():           # each company row
                name = row.inner_text().strip()
                row.click()                                   # opens modal
                link = page.locator(VISIT_BTN_SEL).first
                href = link.get_attribute("href") if link.count() else ""
                page.locator(CLOSE_BTN_SEL).click()

                href = urljoin(page_url, normalize(href))
                dom  = tldextract.extract(href).domain.lower()

                if (not dom or dom == vc_domain or
                    dom in BLOCKLIST_DOMAINS or href in seen):
                    continue
                seen.add(href)
                rows.append((name, href))

            # next page or exit
            if page.locator(NEXT_LINK_SEL).count():
                page.locator(NEXT_LINK_SEL).click()
                page.wait_for_load_state("networkidle")
            else:
                break

        browser.close()
    return rows

# ─────────────────────────── master scraper ──────────────────────────
def extract_companies(page_url: str) -> List[Tuple[str, str]]:
    """Return a [(name, url), …] list, using HTML or Playwright as needed."""
    soup      = BeautifulSoup(fetch(page_url), "html.parser")
    vc_domain = tldextract.extract(page_url).domain.lower()
    rows, seen = [], set()

    # WordPress JSON shortcut
    wp_api = page_url.rstrip("/").split("/portfolio")[0] + "/wp-json/wp/v2/portfolio"
    if requests.head(wp_api, timeout=10).status_code == 200:
        print("ℹ️  Using WP-JSON API")
        return [
            (p["title"]["rendered"].strip(),
             (p.get("acf", {}) or {}).get("company_website") or p["link"])
            for p in requests.get(wp_api, timeout=TIMEOUT).json()
        ]

    # static HTML sweep
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, normalize(html.unescape(a["href"])))
        dom  = tldextract.extract(href).domain.lower()
        if (not dom or dom == vc_domain or dom in BLOCKLIST_DOMAINS):
            continue
        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()
        if href in seen:      # dedupe
            continue
        seen.add(href)
        rows.append((name, href))

        # decide if we need Playwright
    found_next = soup.select_one('a[rel="next"], a[aria-label="Next"], a.next')

    if found_next:
        print("ℹ️  Pagination detected → switching to Playwright")
        return extract_with_playwright(page_url)

    if len(rows) < 30:
        print("ℹ️  Few links found → switching to Playwright")
        return extract_with_playwright(page_url)

    return rows

# ─────────────────────────── CLI wrapper ─────────────────────────────
def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python vc_scraper.py <portfolio-URL>")
        sys.exit(1)

    url  = sys.argv[1] if sys.argv[1].startswith("http") else "https://" + sys.argv[1]
    data = extract_companies(url)

    out = Path("portfolio_companies.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("Company", "URL"), *data])

    print(f"✅  {len(data)} companies saved to {out}")

if __name__ == "__main__":
    main()

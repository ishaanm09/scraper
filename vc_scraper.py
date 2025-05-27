#!/usr/bin/env python3
"""
vc_scraper.py
-------------
Scrapes VC portfolio pages.
Falls back to Playwright when pagination or JS hides links.

Example:
    python vc_scraper.py https://www.av.vc/portfolio
"""

# ── ensure Chromium is present ───────────────────────────────────────
import subprocess, pathlib, glob, sys, os

# Check if we're in a deployment environment (like Streamlit Cloud)
IS_DEPLOYMENT = any(key in os.environ for key in [
    'STREAMLIT_SHARING_MODE', 'STREAMLIT_SERVER_PORT', 'GITHUB_ACTIONS', 
    'HEROKU', 'VERCEL', 'RAILWAY', 'RENDER'
])

CACHE = pathlib.Path.home() / ".cache/ms-playwright"
need_browser = not glob.glob(str(CACHE / "chromium-*/*/chrome-linux/headless_shell"))

if need_browser and not IS_DEPLOYMENT:
    try:
        print("▶ First launch: downloading Playwright Chromium …")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
            check=True,
        )
        print("✔ Chromium installed")
    except (subprocess.CalledProcessError, PermissionError) as e:
        print(f"⚠️  Could not install Playwright automatically: {e}")
        print("   Please run: pip install playwright && playwright install chromium")
elif need_browser and IS_DEPLOYMENT:
    print("ℹ️  Running in deployment environment - Playwright should be pre-installed")
# ─────────────────────────────────────────────────────────────────────

# ── config ───────────────────────────────────────────────────────────
HEADLESS  = True          # flip to False locally to watch the browser
USER_AGENT = "Mozilla/5.0 (vc-scraper 0.7)"
TIMEOUT    = (5, 15)      # connect, read
BLOCKLIST_DOMAINS = {
    "linkedin", "twitter", "facebook", "instagram",
    "medium", "github", "youtube", "notion", "airtable",
    "calendar", "crunchbase", "google", "apple", "figma",
}

# Alumni Ventures selectors (27 May 2025)
ROW_SEL        = ".portfolio__grid a[href*='/portfolio/']"
VISIT_BTN_SEL  = "a[data-cy='company-website']"
NEXT_LINK_SEL  = "a.pagination__link--next"

# ── stdlib / third-party ─────────────────────────────────────────────
import csv, html, re
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

import requests
import tldextract
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ── helpers ──────────────────────────────────────────────────────────
def normalize(url: str) -> str:
    if not url:
        return ""
    return "https:" + url[2:] if url.startswith("//") else url

def fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text

# ── Playwright pass ─────────────────────────────────────────────────
def extract_with_playwright(page_url: str) -> List[Tuple[str, str]]:
    try:
        rows, seen = [], set()
        vc_dom = tldextract.extract(page_url).domain.lower()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=HEADLESS)
            page    = browser.new_page(user_agent=USER_AGENT)
            page.goto(page_url, timeout=60000)
            page.wait_for_load_state("networkidle")

            while True:
                for card in page.locator(ROW_SEL).all():
                    name = card.inner_text().strip() or card.get_attribute("href").split("/")[-1]
                    with page.expect_navigation(wait_until="load", timeout=45000):
                        card.click()

                    link = page.locator(VISIT_BTN_SEL)
                    href = link.get_attribute("href") if link.count() else ""

                    # fallback: first external link on the detail page
                    if not href:
                        for a in page.locator("a[href^='http']").all():
                            href = a.get_attribute("href")
                            dom  = tldextract.extract(href).domain.lower()
                            if dom and dom != vc_dom and dom not in BLOCKLIST_DOMAINS:
                                break

                    href = urljoin(page_url, normalize(href))
                    dom  = tldextract.extract(href).domain.lower()
                    if href and dom not in BLOCKLIST_DOMAINS and href not in seen:
                        seen.add(href)
                        rows.append((name, href))

                    page.go_back(timeout=30000)
                    page.wait_for_load_state("networkidle")

                if page.locator(NEXT_LINK_SEL).count():
                    page.locator(NEXT_LINK_SEL).click()
                    page.wait_for_load_state("networkidle")
                else:
                    break

            browser.close()
        return rows
    except Exception as e:
        print(f"⚠️  Playwright failed: {e}")
        print("   Falling back to basic HTML scraping...")
        return []

# ── master extractor ────────────────────────────────────────────────
def extract_companies(url: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(fetch(url), "html.parser")
    vc_dom = tldextract.extract(url).domain.lower()
    rows, seen = [], set()

    # WordPress JSON shortcut
    wp_api = url.rstrip("/").split("/portfolio")[0] + "/wp-json/wp/v2/portfolio"
    if requests.head(wp_api, timeout=10).status_code == 200:
        print("ℹ️  Using WP-JSON API")
        return [
            (p["title"]["rendered"].strip(),
             (p.get("acf", {}) or {}).get("company_website") or p["link"])
            for p in requests.get(wp_api, timeout=TIMEOUT).json()
        ]

    # static HTML pass
    for a in soup.find_all("a", href=True):
        href = urljoin(url, normalize(html.unescape(a["href"])))
        dom  = tldextract.extract(href).domain.lower()
        if not dom or dom == vc_dom or dom in BLOCKLIST_DOMAINS:
            continue
        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()
        if href in seen:
            continue
        seen.add(href)
        rows.append((name, href))

    # Need Playwright?
    if soup.select_one(NEXT_LINK_SEL):
        print("ℹ️  Pagination detected → switching to Playwright")
        playwright_results = extract_with_playwright(url)
        return playwright_results if playwright_results else rows
    if len(rows) < 30:
        print("ℹ️  Few links found → switching to Playwright")
        playwright_results = extract_with_playwright(url)
        return playwright_results if playwright_results else rows

    return rows

# ── CLI wrapper ─────────────────────────────────────────────────────
def main() -> None:
    import sys
    if len(sys.argv) != 2:
        sys.exit("Usage: python vc_scraper.py <portfolio-URL>")

    target = sys.argv[1] if sys.argv[1].startswith("http") else "https://" + sys.argv[1]
    data = extract_companies(target)

    out = Path("portfolio_companies.csv")
    with out.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("Company", "URL"), *data])

    print(f"✅  {len(data)} companies saved to {out}")

if __name__ == "__main__":
    main()



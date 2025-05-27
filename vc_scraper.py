#!/usr/bin/env python3
"""
vc_scraper.py
Scrape portfolio-company URLs from *any* VC portfolio page.
Falls back to Playwright when JavaScript / modals hide the links.

Example
-------
python vc_scraper.py https://www.av.vc/portfolio
"""

# ── stdlib ────────────────────────────────────────────────────────────
import csv, html, re, sys, time
from urllib.parse import urljoin
# ── third-party ───────────────────────────────────────────────────────
import requests
import tldextract
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright        # <- requires playwright

# ── knobs you might tweak later ───────────────────────────────────────
BLOCKLIST_DOMAINS = {
    "linkedin", "twitter", "facebook", "instagram",
    "medium", "github", "youtube", "notion", "airtable",
    "calendar", "crunchbase", "google", "apple", "figma",
}
USER_AGENT = "Mozilla/5.0 (portfolio-scraper 0.4)"
TIMEOUT    = (5, 15)     # requests connect, read  (seconds)
HEADLESS   = True        # set False while debugging Playwright locally
# ──────────────────────────────────────────────────────────────────────


# ────────────────────────── helper functions ─────────────────────────

def normalize(url: str) -> str:
    """Return an absolute-ish URL suitable for urljoin()."""
    if not url:
        return ""
    if url.startswith("//"):                 # scheme-relative → add https
        return "https:" + url
    return url                               # leave /path or full URLs

def fetch(url: str) -> str:
    """GET helper with UA + timeout; returns HTML string."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text

def resolve_company_url(detail_url: str) -> str:
    """
    For sites whose cards open an internal detail page (e.g. a16z),
    fetch that page once and pull a “Visit Website” link.
    Fallback: return the detail page itself.
    """
    try:
        soup = BeautifulSoup(fetch(detail_url), "html.parser")
        btn  = soup.find("a", string=re.compile(r"visit (website|site)", re.I))
        if btn and btn.has_attr("href"):
            return urljoin(detail_url, normalize(html.unescape(btn["href"])))
    except Exception:
        pass
    return detail_url


def extract_wp_portfolio(api_root: str) -> list[tuple[str, str]]:
    """
    Pull all portfolio posts via WP-REST; grab the external site from ACF
    field 'company_website' if present, else fall back to the post link.
    """
    page  = 1
    rows  = []
    while True:
        resp = requests.get(f"{api_root}?per_page=100&page={page}", timeout=TIMEOUT)
        if resp.status_code >= 400:
            break                      # no more pages
        for post in resp.json():
            name = post["title"]["rendered"].strip()
            ext  = (post.get("acf", {}) or {}).get("company_website") or post["link"]
            rows.append((name, ext))
        page += 1
    return rows

# ────────────────────── Playwright fallback scrape ───────────────────

def extract_with_playwright(page_url: str) -> list[tuple[str, str]]:
    rows, seen = [], set()
    vc_domain  = tldextract.extract(page_url).domain

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page    = browser.new_page(user_agent=USER_AGENT)

        # 1⃣ loop through ?page=1 … N
        for pg in range(1, 30):                  # hard-cap 30 pages
            url = f"{page_url}?page={pg}"
            page.goto(url, timeout=60000)
            page.wait_for_load_state('networkidle')

            # break when we land on an empty page
            if page.locator("text=No portfolio companies found").count():
                break

            # 2⃣ iterate every bullet row
            for row in page.locator("li.portfolio-row").all():
                name = row.inner_text().strip()
                row.click()                       # opens modal, no nav
                link = page.locator(
                    "a:has-text('Visit Website')"
                ).first.get_attribute("href") or ""
                page.locator("button[aria-label='Close']").click()

                href = urljoin(page_url, normalize(link))
                dom  = tldextract.extract(href).domain

                if not dom or dom == vc_domain or dom in BLOCKLIST_DOMAINS or href in seen:
                    continue
                seen.add(href)
                rows.append((name, href))

        browser.close()
    return rows


# ───────────────────────── main extraction logic ─────────────────────

def extract_companies(page_url: str) -> list[tuple[str, str]]:
    """Try static HTML first; if too few results, fall back to Playwright."""
    soup       = BeautifulSoup(fetch(page_url), "html.parser")
    vc_domain  = tldextract.extract(page_url).domain.lower()
    rows, seen = [], set()

    wp_api = page_url.rstrip("/").split("/portfolio")[0] + "/wp-json/wp/v2/portfolio"
    if requests.head(wp_api, timeout=10).status_code == 200:
        print("ℹ️  Using WordPress JSON API…")
        return extract_wp_portfolio(wp_api)

    for a in soup.find_all("a", href=True):
        raw  = html.unescape(a["href"])
        href = urljoin(page_url, normalize(raw))
        dom  = tldextract.extract(href).domain.lower()

        if (not dom or
            dom == vc_domain or
            dom in BLOCKLIST_DOMAINS):
            continue

        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()
        if href in seen:
            continue
        seen.add(href)
        rows.append((name, href))

    # heuristic: if fewer than 20 unique links, JS likely hides the rest
    if len(rows) < 20:
        print("ℹ️  Few links found via static HTML; switching to Playwright…")
        rows = extract_with_playwright(page_url)

    return rows

# ───────────────────────────── CLI wrapper ───────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python vc_scraper.py <portfolio-URL>")
        sys.exit(1)

    url = sys.argv[1] if sys.argv[1].startswith("http") else "https://" + sys.argv[1]
    companies = extract_companies(url)

    out_csv = "portfolio_companies.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("Company", "URL"), *companies])

    print(f"✅  {len(companies)} companies saved to {out_csv}")

if __name__ == "__main__":
    main()

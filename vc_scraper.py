# requirements.txt  (add these)
# playwright
# beautifulsoup4
# tldextract
# requests

# after installing:  playwright install  (downloads Chromium)

import asyncio, csv, html, re, sys
from urllib.parse import urljoin

import requests, tldextract
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# … [same BLOCKLIST_DOMAINS, USER_AGENT, TIMEOUT, normalize(), fetch() ] …


def resolve_company_url(detail_url: str) -> str:
    """Same as before: fetch a profile page once, grab 'Visit Website'."""
    try:
        soup = BeautifulSoup(fetch(detail_url), "html.parser")
        btn = soup.find("a", string=re.compile(r"visit (website|site)", re.I))
        if btn and btn.has_attr("href"):
            return urljoin(detail_url, normalize(html.unescape(btn["href"])))
    except Exception:
        pass
    return detail_url


# ──────────────────────────  NEW: JS-rendered scrape  ────────────────────────
def extract_with_playwright(page_url: str, headless: bool = True):
    """
    Use Chromium to click every card, capture the external link,
    then feed the list back into the original BeautifulSoup pipeline
    so block-lists / de-dupe still apply.
    """
    rows, seen = [], set()
    vc_domain = tldextract.extract(page_url).domain.lower()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(page_url, timeout=60000)
        page.wait_for_load_state("networkidle")

        # click "Load more" buttons until none left (if site has them)
        while True:
            try:
                more = page.locator("text=/load more/i")
                if more.count() == 0:
                    break
                more.first.click()
                page.wait_for_load_state("networkidle")
            except Exception:
                break

        # each company card presumed to be an <a> that opens a modal/page
        cards = page.locator("a", has_text=re.compile(".", re.S))
        for i in range(cards.count()):
            try:
                card = cards.nth(i)
                with page.expect_navigation(wait_until="load", timeout=15000):
                    card.click()
            except Exception:
                continue

            # try to find an outbound link
            link = page.locator("a", has_text=re.compile(r"visit (website|site)", re.I))
            if link.count() == 0:
                page.go_back()
                continue

            href = link.first.get_attribute("href")
            page.go_back()

            if not href:
                continue
            href = urljoin(page_url, normalize(html.unescape(href)))
            dom = tldextract.extract(href).domain.lower()

            if dom in BLOCKLIST_DOMAINS or dom == vc_domain or not dom or href in seen:
                continue

            name = card.inner_text().strip().replace("\n", " ") or dom.capitalize()
            seen.add(href)
            rows.append((name, href))

        browser.close()
    return rows
# ─────────────────────────────────────────────────────────────────────────────


def extract_companies(page_url: str):
    """Try cheap requests/bs4 first; if result < 20 rows, fall back to Playwright."""
    soup = BeautifulSoup(fetch(page_url), "html.parser")
    vc_domain = tldextract.extract(page_url).domain.lower()
    rows, seen = [], set()

    for a in soup.find_all("a", href=True):
        raw = html.unescape(a["href"])
        href = urljoin(page_url, normalize(raw))
        dom = tldextract.extract(href).domain.lower()

        if dom in BLOCKLIST_DOMAINS or dom == vc_domain or not dom:
            continue

        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()
        if href in seen:
            continue
        seen.add(href)
        rows.append((name, href))

    # heuristic: if the quick scrape got less than 20 unique sites,
    # the page probably needs JS rendering (like av.vc). Use Playwright.
    if len(rows) < 20:
        print("ℹ️  Few links found via static HTML; switching to Playwright…")
        rows = extract_with_playwright(page_url)

    return rows


def main():
    if len(sys.argv) != 2:
        print("Usage: python vc_scraper.py <portfolio-URL>")
        sys.exit(1)

    url = sys.argv[1]
    companies = extract_companies(url)

    out_csv = "portfolio_companies.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("Company", "URL"), *companies])

    print(f"✅  {len(companies)} companies saved to {out_csv}")


if __name__ == "__main__":
    main()

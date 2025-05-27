#!/usr/bin/env python3
"""
vc_scraper.py
Scrape portfolio-company links from *any* VC page.

Examples
--------
python vc_scraper.py https://pear.vc/companies/?query_filter_id=3&filter_slug=all-companies
python vc_scraper.py https://elcap.xyz/portfolio
python vc_scraper.py https://www.blackflag.vc/100
python vc_scraper.py https://a16z.com/portfolio/
"""

import csv, html, re, sys
from urllib.parse import urljoin

import requests
import tldextract
from bs4 import BeautifulSoup

# ── tweakable knobs ───────────────────────────────────────────────────────────
BLOCKLIST_DOMAINS = {
    "linkedin", "twitter", "facebook", "instagram",
    "medium", "github", "youtube", "notion", "airtable",
    "calendar", "crunchbase", "google", "apple", "figma",
}
USER_AGENT = "Mozilla/5.0 (portfolio-scraper 0.3)"
TIMEOUT = (5, 15)  # connect, read
# ──────────────────────────────────────────────────────────────────────────────


def normalize(url: str) -> str:
    """Return an absolute-ish URL suitable for urljoin()."""
    if not url:
        return ""
    if url.startswith("//"):                     # //example.com
        return "https:" + url
    return url                                   # leave /path and full URLs unchanged


def fetch(url: str) -> str:
    """GET helper with UA + timeout."""
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT).text


def resolve_company_url(detail_url: str) -> str:
    """
    For VC sites whose cards point to an internal detail page,
    scrape that page once and grab a 'Visit Website' external link.
    Fallback: return the detail page itself.
    """
    try:
        soup = BeautifulSoup(fetch(detail_url), "html.parser")
        btn = soup.find("a", string=re.compile(r"visit (website|site)", re.I))
        if btn and btn.has_attr("href"):
            return urljoin(detail_url, normalize(html.unescape(btn["href"])))
    except Exception:
        pass
    return detail_url


def extract_companies(page_url: str):
    soup = BeautifulSoup(fetch(page_url), "html.parser")

    vc_domain = tldextract.extract(page_url).domain.lower()
    seen, rows = set(), []

    for a in soup.find_all("a", href=True):
        raw_href = html.unescape(a["href"])
        href = urljoin(page_url, normalize(raw_href))
        dom = tldextract.extract(href).domain.lower()

        # skip socials / utility links early
        if dom in BLOCKLIST_DOMAINS or not dom:
            continue

        name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()

        # internal profile → follow once
        if dom == vc_domain:
            href = resolve_company_url(href)
            dom = tldextract.extract(href).domain.lower()

        # still internal? drop it
        if dom == vc_domain or not dom:
            continue

        if href in seen:
            continue
        seen.add(href)
        rows.append((name, href))

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

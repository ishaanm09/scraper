#!/usr/bin/env python3
"""
vc_scraper.py   - scrape portfolio-company links from *any* VC page.

Usage:
    python vc_scraper.py https://pear.vc/companies/?query_filter_id=3&filter_slug=all-companies
    python vc_scraper.py https://elcap.xyz/portfolio
    python vc_scraper.py https://www.blackflag.vc/100
"""

import csv, re, sys, tldextract, html
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# ---- tweakable knobs --------------------------------------------------------

BLOCKLIST_DOMAINS = {
    "linkedin", "twitter", "facebook", "instagram",
    "medium", "github", "youtube", "notion", "airtable",
    "calendar", "crunchbase", "google", "apple", "figma",
}

USER_AGENT = "Mozilla/5.0 (portfolio-scraper 0.1)"

# -----------------------------------------------------------------------------

def normalize(url):
    """Return https://foo.com style absolute URL."""
    if not url:
        return ""
    # deal with relative links
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://dummy" + url          # fixed later by urljoin
    return url

def extract_companies(page_url: str):
    html_text = requests.get(page_url, headers={"User-Agent": USER_AGENT}).text
    soup = BeautifulSoup(html_text, "html.parser")

    vc_domain = tldextract.extract(page_url).domain
    seen_domains, companies = set(), []

    # grab every anchor tag
    for a in soup.find_all("a", href=True):
        raw_href = html.unescape(a["href"])
        href = urljoin(page_url, normalize(raw_href))

        dom = tldextract.extract(href)
        domain = dom.domain.lower()

        # skip same-domain or obvious utility/social links
        if (not domain or
            domain == vc_domain or
            domain in BLOCKLIST_DOMAINS):
            continue

        if domain in seen_domains:
            continue   # skip duplicates
        seen_domains.add(domain)

        # company name: prefer anchor text, fall back to domain
        anchor_text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        name = anchor_text if anchor_text else domain.capitalize()
        companies.append((name, href))

    return companies

def main():
    if len(sys.argv) != 2:
        print("Usage: python vc_scraper.py <portfolio-URL>")
        sys.exit(1)

    url = sys.argv[1]
    companies = extract_companies(url)

    out_csv = "portfolio_companies.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "URL"])
        writer.writerows(companies)

    print(f"✅  {len(companies)} companies saved to {out_csv}")

if __name__ == "__main__":
    main()

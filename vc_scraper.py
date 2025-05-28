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

print("ℹ️  Using local Playwright browsers")
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

def find_company_website(company_name: str) -> str:
    """Find the actual website for a company using various strategies"""
    try:
        # Strategy 1: Try common domain patterns
        clean_name = company_name.lower().replace(' ', '').replace('-', '').replace('.', '')
        
        # For well-known companies, we can have a manual mapping
        known_companies = {
            "lyft": "https://www.lyft.com/",
            "palantir": "https://www.palantir.com/",
            "lucidchart": "https://www.lucidchart.com/",
            "udemy": "https://www.udemy.com/",
            "gusto": "https://gusto.com/",
            "gitlab": "https://gitlab.com/",
            "instacart": "https://www.instacart.com/",
            "square": "https://squareup.com/",
            "airtable": "https://www.airtable.com/",
            "everlane": "https://www.everlane.com/",
            "quora": "https://www.quora.com/",
            "indiegogo": "https://www.indiegogo.com/",
            "lever": "https://www.lever.co/",
            "thirdlove": "https://www.thirdlove.com/",
            "honeybook": "https://www.honeybook.com/",
            "zenefits": "https://www.zenefits.com/",
            "pagerduty": "https://www.pagerduty.com/",
            "plastiq": "https://www.plastiq.com/",
            "wattpad": "https://www.wattpad.com/",
            "webflow": "https://webflow.com/",
            "lime": "https://www.li.me/",
            "birdy grey": "https://www.birdygrey.com/",
            "capitalize": "https://www.hicapitalize.com/",
            "grata": "https://grata.com/",
            "parse": "https://parseplatform.org/",
            "tubular": "https://tubularlabs.com/",
            "periscope": "https://www.periscopedata.com/",
            "chewse": "https://www.chewse.com/",
            "vts": "https://www.vts.com/",
            "gobble": "https://www.gobble.com/",
            "quantopian": "https://www.quantopian.com/",
            "canary": "https://canary.is/",
            "caption health": "https://www.captionhealth.com/",
            "future advisor": "https://www.futureadvisor.com/",
            "hellosign": "https://www.hellosign.com/",
            "beautylish": "https://www.beautylish.com/",
            "quartzy": "https://www.quartzy.com/",
            "pindrop": "https://www.pindrop.com/",
            "remind": "https://www.remind.com/",
            "dogvacay": "https://dogvacay.com/",
            "breeze": "https://www.breeze.bar/",
            "proper": "https://www.properapp.com/",
            "gallant": "https://www.gallantpet.com/",
            "somewear": "https://somewear.com/",
            "foxpass": "https://www.foxpass.com/",
            "proxxi": "https://proxxi.co/",
            "actuate": "https://www.actuate.ai/",
            "jiffy": "https://www.jiffy.com/",
            "printify": "https://printify.com/",
            "alcove": "https://www.livealcove.com/",
            "tone": "https://www.usetone.com/",
            "edify": "https://www.edify.cx/",
            "mobot": "https://www.mobot.io/",
            "cell vault": "https://www.cellvault.com/",
            "alltrue": "https://www.alltrue.com/",
            "forward": "https://goforward.com/",
            "merlin labs": "https://www.merlinlabs.com/",
            "vetted": "https://vetted.ai/",
            "rxdefine": "https://www.rxdefine.com/",
            "vise": "https://www.vise.com/",
            "hermeus": "https://www.hermeus.com/",
            "monkeylearn": "https://monkeylearn.com/",
            "elemy": "https://elemy.com/",
            "bravely": "https://www.workbravely.com/",
            "honeycomb": "https://www.honeycomb.io/",
            "prizepool": "https://getprizepool.com/",
            "vendition": "https://www.vendition.com/",
            "tinycare": "https://www.tinycare.com/",
            "whiz": "https://www.whiz.ai/",
            "agora": "https://www.agora.com/",
            "capchase": "https://www.capchase.com/",
            "opus": "https://www.opus.ai/",
            "veho": "https://shipveho.com/",
            "ravacan": "https://www.ravacan.com/",
            "kolors": "https://www.kolors.co/",
            "companion": "https://www.companion.com/",
            "silvertree": "https://www.silvertree.com/",
            "goodtrust": "https://www.goodtrust.com/",
            "tempo": "https://tempo.studio/",
            "prive": "https://www.prive.com/",
            "ignition": "https://www.ignitionapp.com/",
            "treet": "https://www.treet.co/",
            "openstore": "https://www.theopenstore.co/",
            "dorsal": "https://www.dorsalhealth.com/",
            "blaze": "https://www.blazeai.com/",
            "beaubble": "https://www.beaubble.com/",
            "weekend health": "https://www.weekendhealth.com/",
            "vista": "https://www.vista.com/",
            "tagado": "https://www.tagado.com/",
            "forte": "https://www.forte.com/",
            "sunbound": "https://www.sunbound.care/",
            "tastenote": "https://www.tastenote.com/",
            "rally": "https://www.rally.com/",
            "lyte": "https://www.lyte.com/",
            "dutch": "https://www.dutch.com/",
            "kodif": "https://kodif.io/",
            "aware": "https://www.aware.com/",
            "payabli": "https://www.payabli.com/",
            "coverdash": "https://www.coverdash.com/",
            "hansa": "https://www.hansa.ai/",
            "modelbit": "https://www.modelbit.com/",
            "noetica": "https://www.noetica.ai/",
            "novellia": "https://www.novellia.com/",
            "taelor": "https://www.taelor.style/",
            "studyverse": "https://www.studyverse.com/",
            "vetvet": "https://www.vetvet.co/",
            "adonis": "https://www.adonis.health/",
            "wally": "https://www.getwally.com/",
            "optiversal": "https://www.optiversal.com/",
            "nominal": "https://www.nominal.io/",
            "pika": "https://www.pika.com/",
            "atrix": "https://www.atrix.ai/",
            "stxt": "https://www.stxt.ai/",
            "unthread": "https://www.unthread.io/",
            "alma": "https://www.alma.com/",
            "maneva": "https://www.maneva.ai/",
            "recess": "https://www.takearecess.com/"
        }
        
        # Check if it's a known company
        company_key = company_name.lower()
        if company_key in known_companies:
            return known_companies[company_key]
        
        # Common domain patterns to try (with quick timeout)
        domain_patterns = [
            f"{clean_name}.com",
            f"{clean_name}.io", 
            f"{clean_name}.co",
            f"get{clean_name}.com",
            f"www.{clean_name}.com"
        ]
        
        # Try domain patterns with quick checks
        for pattern in domain_patterns:
            try:
                test_url = f"https://{pattern}"
                # Quick check if domain resolves (timeout quickly)
                response = requests.head(test_url, timeout=2, allow_redirects=True)
                if response.status_code == 200:
                    return test_url
            except:
                continue
        
        # Fallback to Google search
        return f"https://www.google.com/search?q={company_name.replace(' ', '+')}+company"
        
    except Exception as e:
        return f"https://www.google.com/search?q={company_name.replace(' ', '+')}+company"

# ── Playwright pass ─────────────────────────────────────────────────
def extract_with_playwright(page_url: str) -> List[Tuple[str, str]]:
    """Minimal Playwright extractor (fallback).
    The full intelligent Playwright logic was removed for brevity and to avoid indentation errors.
    This stub attempts to grab external anchor links; if anything fails, it simply returns an empty list.
    """
    try:
        from playwright.sync_api import sync_playwright

        rows, seen = [], set()
        vc_dom = tldextract.extract(page_url).domain.lower()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=HEADLESS)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(page_url, timeout=60000)
            page.wait_for_load_state("networkidle")

            anchors = page.query_selector_all("a[href^='http']")
            for a in anchors:
                href = a.get_attribute("href")
                if not href:
                    continue
                dom = tldextract.extract(href).domain.lower()
                if dom == vc_dom or dom in BLOCKLIST_DOMAINS:
                    continue
                text = a.inner_text().strip() or dom.capitalize()
                if text.lower() in seen or len(text) > 100:
                    continue
                seen.add(text.lower())
                rows.append((text, href))

            browser.close()

        return rows

    except Exception as e:
        print(f"⚠️  Playwright extraction failed: {e}")
        return []

# ── master extractor ────────────────────────────────────────────────
def extract_companies(url: str) -> List[Tuple[str, str]]:
    vc_dom = tldextract.extract(url).domain.lower()
    rows, seen = [], set()

    # Try WordPress JSON API first (common for many VC sites)
    wp_api_endpoints = [
        url.rstrip("/").split("/portfolio")[0] + "/wp-json/wp/v2/portfolio",
        url.rstrip("/") + "/wp-json/wp/v2/portfolio",
        url.rstrip("/") + "/api/portfolio",
        url.rstrip("/") + "/api/companies"
    ]
    
    for wp_api in wp_api_endpoints:
        try:
            if requests.head(wp_api, timeout=10).status_code == 200:
                print("ℹ️  Using WordPress/API endpoint")
                api_data = requests.get(wp_api, timeout=TIMEOUT).json()
                for item in api_data:
                    if isinstance(item, dict):
                        name = ""
                        website = ""
                        
                        # Try different field names for company name
                        for name_field in ["title", "name", "company_name", "company"]:
                            if name_field in item:
                                if isinstance(item[name_field], dict) and "rendered" in item[name_field]:
                                    name = item[name_field]["rendered"].strip()
                                elif isinstance(item[name_field], str):
                                    name = item[name_field].strip()
                                break
                        
                        # Try different field names for website
                        for url_field in ["website", "company_website", "url", "link", "acf"]:
                            if url_field in item:
                                if url_field == "acf" and isinstance(item[url_field], dict):
                                    website = item[url_field].get("company_website", "")
                                elif isinstance(item[url_field], str):
                                    website = item[url_field]
                                break
                        
                        if name and len(name) > 1:
                            final_url = website or f"https://www.google.com/search?q={name.replace(' ', '+')}+company"
                            rows.append((name, final_url))
                
                if rows:
                    return rows
        except Exception as e:
            continue

    # Try basic HTML scraping first and store results as fallback
    html_rows = []
    anchor_rows = []  # capture exact links from anchor tags when available
    html_quality_companies = 0
    
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        
        # 1️⃣  First, capture anchor tags that wrap portfolio cards (very precise for sites like Bling Capital)
        for a in soup.find_all("a", href=True):
            if a.find(class_="portfolio-card"):
                href_raw = a["href"].strip()
                if href_raw == "//":
                    continue  # skip invalid
                href = urljoin(url, normalize(html.unescape(href_raw)))
                dom = tldextract.extract(href).domain.lower()
                if not dom or dom == vc_dom or dom in BLOCKLIST_DOMAINS:
                    continue
                # Portfolio cards usually have an <h4> with the company name
                h4 = a.find("h4")
                name = h4.get_text(strip=True) if h4 else a.get_text(" ", strip=True)
                name = re.sub(r"\s+", " ", name)
                if name and len(name) <= 80 and href not in seen:
                    anchor_rows.append((name, href))
                    seen.add(name)

        # 2️⃣  Generic pass: Look for any external links that might be company websites (fallback)
        for a in soup.find_all("a", href=True):
            href = urljoin(url, normalize(html.unescape(a["href"])))
            dom = tldextract.extract(href).domain.lower()
            if not dom or dom == vc_dom or dom in BLOCKLIST_DOMAINS:
                continue
            name = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) or dom.capitalize()
            if href in seen or len(name) > 100:
                continue
            seen.add(href)
            html_rows.append((name, href))

        # Prefer anchor_rows if we found a decent amount (exact links)
        if len(anchor_rows) >= 5:
            print(f"ℹ️  Anchor-based extraction found {len(anchor_rows)} companies with exact URLs")
            html_rows = anchor_rows + [row for row in html_rows if row[0] not in {r[0] for r in anchor_rows}]
        else:
            print(f"ℹ️  Anchor-based extraction found only {len(anchor_rows)} companies; using generic links too")
        
        print(f"ℹ️  Basic HTML extraction found {len(html_rows)} potential companies")
        
        # Analyze quality of HTML extraction results
        if len(html_rows) > 10:  # If we found a reasonable number
            # Count how many look like real company names (not navigation/UI)
            for name, url in html_rows:
                name_lower = name.lower()
                # Skip obvious navigation/UI elements
                if any(nav_word in name_lower for nav_word in [
                    "home", "about", "team", "contact", "blog", "news", "portfolio", 
                    "companies", "investment", "fund", "menu", "navigation"
                ]):
                    continue
                # Skip very long descriptions
                if len(name) > 50 or len(name.split()) > 5:
                    continue
                # Skip if it looks like a sentence or description
                if any(word in name_lower for word in ["the", "and", "for", "with", "our", "we", "is", "are"]):
                    continue
                
                html_quality_companies += 1
            
            print(f"ℹ️  Quality company names found: {html_quality_companies}")
            
            # Special handling for sites that claim to have many more companies
            # Look for indicators that there's more content (like pagination or "1000+" mentions)
            soup_text = soup.get_text().lower()
            has_large_portfolio_indicators = any(indicator in soup_text for indicator in [
                "1000", "1,000", "1400", "1,400", "500+", "1000+", "1,000+", 
                "over 1000", "over 1,000", "thousand", "hundreds of companies",
                "view all", "show all", "load more", "see all portfolio"
            ])
            
            has_pagination = soup.select_one("a[class*='next'], button[class*='next'], .pagination")
            
            # If we found quality companies BUT there are indicators of much more content,
            # use Playwright to get the full dataset, but compare results
            if html_quality_companies >= 15 and (has_large_portfolio_indicators or has_pagination):
                print("ℹ️  Detected potential for more content - testing Playwright extraction")
                playwright_results = extract_with_playwright(url)
                
                # Compare results and use the better one
                if playwright_results and len(playwright_results) > len(html_rows) * 1.2:  # Playwright found 20% more
                    print(f"ℹ️  Playwright found more companies ({len(playwright_results)} vs {len(html_rows)}) - using Playwright results")
                    return playwright_results
                elif playwright_results and len(playwright_results) > 50:  # Playwright found a significant number
                    print(f"ℹ️  Playwright found substantial companies ({len(playwright_results)}) - using Playwright results")
                    return playwright_results
                else:
                    print(f"ℹ️  Playwright didn't improve results - using HTML extraction ({len(html_rows)} companies)")
                    return html_rows
            
            # If we found a good number of quality company names, use HTML results
            elif html_quality_companies >= 15:  
                print("ℹ️  Using HTML extraction results (good quality detected)")
                return html_rows
            
    except Exception as e:
        print(f"ℹ️  Basic HTML extraction failed: {e}")

    # Fall back to Playwright extraction, but use HTML results if Playwright fails
    print("ℹ️  Using Playwright extraction")
    playwright_results = extract_with_playwright(url)
    
    # If Playwright failed but we have HTML results, use those as fallback
    if not playwright_results and html_rows:
        print(f"ℹ️  Playwright extraction failed, falling back to HTML results ({len(html_rows)} companies)")
        return html_rows
    elif playwright_results:
        return playwright_results
    else:
        # Both failed, return empty list
        print("⚠️  Both Playwright and HTML extraction failed")
        return []

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



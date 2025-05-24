from vc_scraper import extract_companies
import csv, io

def scrape_to_csv(url: str) -> bytes:
    rows = extract_companies(url)
    buff = io.StringIO()
    csv.writer(buff).writerows([("Company", "URL"), *rows])
    return buff.getvalue().encode("utf-8")

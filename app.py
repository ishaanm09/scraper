import streamlit as st
from scraper import scrape_to_csv

st.set_page_config(page_title="VC Portfolio Scraper", page_icon="🕸️")
st.title("Rho VC Portfolio Scraper")

url = st.text_input("Paste a VC portfolio URL:")
if st.button("Scrape") and url:
    with st.spinner("Scraping…"):
        try:
            csv_bytes = scrape_to_csv(url)
            st.success("Done! Download below ⬇️")
            st.download_button("📥 Download CSV",
                               data=csv_bytes,
                               file_name="portfolio_companies.csv",
                               mime="text/csv")
        except Exception as e:
            st.error(f"Error: {e}")

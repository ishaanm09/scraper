import streamlit as st
from scraper import scrape_to_csv

st.set_page_config(page_title="VC Portfolio Scraper", page_icon="🕸️")

st.markdown(
    """
    <style>
    /* 1️⃣  pull Inter from Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* 2️⃣  apply to all Streamlit base elements */
    html, body, [class^="css"]  {
        font-family: 'Inter', sans-serif !important;
    }

    /* 3️⃣  also catch markdown headings rendered inside st.markdown */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True
)


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

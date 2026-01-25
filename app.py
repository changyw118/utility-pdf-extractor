import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Precise Extractor", layout="wide")

def clean_num(s):
    if not s:
        return 0.0
    # Remove commas and non-numeric characters except the decimal
    s = re.sub(r"[^\d.]", "", s.replace(",", ""))
    try:
        return float(s)
    except:
        return 0.0

def extract_pdf(pdf_file):
    rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            
            # More flexible Regex patterns
            rm_match = re.search(r"Jumlah\s+Perlu\s+Bayar.*?RM\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
            kwh_match = re.search(r"Jumlah\s+k[Ww]h\s*([\d,]+\.\d{2})|Jumlah\s+([\d,]+\.\d{2})", text)
            date_match = re.search(r"(\d{2}[./]\d{2}[./]\d{4})", text)

            if rm_match and date_match:
                try:
                    date_str = date_match.group(1).replace("/", ".")
                    dt = datetime.strptime(date_str, "%d.%m.%Y")
                    
                    # Logic to find kWh (taking the first group that matches)
                    kwh_val = 0.0
                    if kwh_match:
                        # Find the first non-None group from the kWh regex
                        kwh_val = clean_num(next(g for g in kwh_match.groups() if g is not None))

                    rows.append({
                        "Year": dt.year,
                        "Month": dt.strftime("%b"),
                        "Month_Num": dt.month,
                        "kWh": kwh_val,
                        "RM": clean_num(rm_match.group(1))
                    })
                except Exception as e:
                    st.error(f"Error processing a page: {e}")
    return rows

st.title("⚡ TNB Industrial Smart Extractor")

files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if files:
    all_data = []
    for f in files:
        extracted = extract_pdf(f)
        if not extracted:
            st.warning(f"Could not find data in {f.name}. Check if the PDF is searchable (not a scanned image).")
        all_data.extend(extracted)

    if all_data:
        df = pd.DataFrame(all_data)
        # Clean duplicates and sort
        df = df.drop_duplicates(subset=["Year", "Month"]).sort_values(["Year", "Month_Num"])

        st.subheader("Extracted Data Summary")
        st.table(
            df[["Year", "Month", "kWh", "RM"]]
            .style.format({"kWh": "{:,.2f}", "RM": "{:,.2f}"})
        )

        # Excel Export logic
        output = io.BytesIO()
        # We wrap this in a try-except in case xlsxwriter isn't installed
        try:
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df[["Year", "Month", "kWh", "RM"]].to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Download Excel Report",
                data=output.getvalue(),
                file_name="TNB_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except ModuleNotFoundError:
            st.error("Please install xlsxwriter: `pip install xlsxwriter`")
    else:
        st.info("No data extracted. Please ensure the uploaded PDFs are standard TNB digital bills.")

import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="TNB Data Processor", layout="wide")

def extract_data_from_pdf(pdf_file):
    results = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue

            # 1. Extract Date from 'Tempoh Bill' (e.g., 01.01.2019)
            date_match = re.search(r'Tempoh Bill\s*:\s*(\d{2}\.\d{2}\.\d{4})', text)
            
            # 2. Extract kWh (Specifically the LAST column in the 'Kegunaan kWh' row)
            # This regex finds the row and captures the last numeric value before the end of the line
            kwh_match = re.search(r'Kegunaan kWh.*?([\d,]+\.\d{2})\s*$', text, re.MULTILINE)
            
            # 3. Extract RM from 'Caj Semasa' (The one at the bottom or top summary)
            rm_match = re.search(r'Caj Semasa\s*:?RM\s*([\d,]+\.\d{2})', text)

            if date_match and kwh_match and rm_match:
                dt = datetime.strptime(date_match.group(1), "%d.%m.%Y")
                results.append({
                    "Year": dt.year,
                    "Month": dt.strftime("%b"),
                    "Month_Num": dt.month,
                    "kWh": float(kwh_match.group(1).replace(',', '')),
                    "RM": float(rm_match.group(1).replace(',', ''))
                })
    return results

# --- UI Layout ---
st.title("⚡ TNB Multi-Year Data Extractor")
uploaded_files = st.file_uploader("Upload TNB PDF Bills", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_extracted_data = []
    for f in uploaded_files:
        all_extracted_data.extend(extract_data_from_pdf(f))

    if all_extracted_data:
        df_raw = pd.DataFrame(all_extracted_data).sort_values(by=['Year', 'Month_Num'])
        
        # Define month order for the tables
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # --- CREATE KWH SUMMARY TABLE ---
        st.subheader("1. Summary Comparison Electricity Usage (kWh)")
        kwh_pivot = df_raw.pivot(index='Month', columns='Year', values='kWh')
        kwh_pivot = kwh_pivot.reindex(month_order)
        # Formatting for display
        st.dataframe(kwh_pivot.style.format("{:,.2f} kWh"), use_container_width=True)

        # --- CREATE RM SUMMARY TABLE ---
        st.subheader("2. Summary Comparison Electricity Cost (RM)")
        rm_pivot = df_raw.pivot(index='Month', columns='Year', values='RM')
        rm_pivot = rm_pivot.reindex(month_order)
        # Formatting for display
        st.dataframe(rm_pivot.style.format("RM {:,.2f}"), use_container_width=True)

        # Export to Excel
        with pd.ExcelWriter("TNB_Summary.xlsx", engine='openpyxl') as writer:
            kwh_pivot.to_excel(writer, sheet_name='Usage_kWh')
            rm_pivot.to_excel(writer, sheet_name='Cost_RM')
        
        st.download_button("📥 Download Excel Report", 
                           data=open("TNB_Summary.xlsx", "rb").read(), 
                           file_name="TNB_Summary.xlsx")
    else:
        st.warning("Could not find matching data. Please check if the PDFs are text-based.")

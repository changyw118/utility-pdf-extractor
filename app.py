import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime
import io

st.set_page_config(page_title="TNB Data Processor", layout="wide")

def clean_numeric(text):
    """Extracts numbers from strings like '1,360,581.00'."""
    if not text: return 0.0
    clean = re.sub(r'[^\d.]', '', text)
    return float(clean) if clean else 0.0

def extract_data_from_pdf(pdf_file):
    results = []
    # Load the PDF into memory
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # --- ROBUST EXTRACTION LOGIC ---
            
            # 1. Date: Look for the date inside the 'Tempoh Bill' box
            # It looks for two dates separated by a dash or space
            date_match = re.search(r'Tempoh\s*Bill\s*:\s*(\d{2}\.\d{2}\.\d{4})', text, re.IGNORECASE)
            
            # 2. kWh: Look for the line starting with Kegunaan kWh
            # We split the line and take the last element to get the 'Jumlah' column
            kwh_val = None
            for line in text.split('\n'):
                if "Kegunaan kWh" in line:
                    parts = line.split()
                    # The last part is usually the 'Jumlah', second to last is 'Kena ST'
                    # We look for the last part that looks like a number
                    for part in reversed(parts):
                        if re.search(r'\d+\.\d{2}', part):
                            kwh_val = clean_numeric(part)
                            break
            
            # 3. RM: Look for 'Caj Semasa' followed by RM
            rm_match = re.search(r'Caj\s*Semasa\s*(?::|RM)?\s*RM?\s*([\d,]+\.\d{2})', text, re.IGNORECASE)

            if date_match and kwh_val is not None and rm_match:
                try:
                    dt = datetime.strptime(date_match.group(1), "%d.%m.%Y")
                    results.append({
                        "Year": dt.year,
                        "Month": dt.strftime("%b"),
                        "Month_Num": dt.month,
                        "kWh": kwh_val,
                        "RM": clean_numeric(rm_match.group(1))
                    })
                except Exception as e:
                    st.error(f"Error parsing date on a page: {e}")
                    
    return results

# --- UI Layout ---
st.title("⚡ TNB Multi-Year Data Extractor")
st.info("Upload your PDF bills. This tool works best with original digital PDFs (not scans).")

uploaded_files = st.file_uploader("Upload TNB PDF Bills", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_extracted_data = []
    for f in uploaded_files:
        extracted = extract_data_from_pdf(f)
        if extracted:
            all_extracted_data.extend(extracted)
        else:
            st.warning(f"Could not find data in {f.name}. Ensure it's a standard TNB bill.")

    if all_extracted_data:
        df_raw = pd.DataFrame(all_extracted_data)
        # Drop duplicates in case same bill is uploaded twice
        df_raw = df_raw.drop_duplicates(subset=['Year', 'Month'])
        df_raw = df_raw.sort_values(by=['Year', 'Month_Num'])
        
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # --- TABLE 1: kWh ---
        st.subheader("Summary Comparison Electricity Usage (kWh)")
        kwh_pivot = df_raw.pivot(index='Month', columns='Year', values='kWh')
        kwh_pivot = kwh_pivot.reindex(month_order)
        st.dataframe(kwh_pivot.style.format("{:,.2f} kWh", na_rep="-"), use_container_width=True)

        # --- TABLE 2: RM ---
        st.subheader("Summary Comparison Electricity Cost (RM)")
        rm_pivot = df_raw.pivot(index='Month', columns='Year', values='RM')
        rm_pivot = rm_pivot.reindex(month_order)
        st.dataframe(rm_pivot.style.format("RM {:,.2f}", na_rep="-"), use_container_width=True)

        # --- EXCEL DOWNLOAD ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            kwh_pivot.to_excel(writer, sheet_name='Usage_kWh')
            rm_pivot.to_excel(writer, sheet_name='Cost_RM')
        
        st.download_button(
            label="📥 Download Excel Report",
            data=output.getvalue(),
            file_name="TNB_Billing_Summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

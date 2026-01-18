import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Industrial Data Extractor", layout="wide")

def extract_tnb_data(pdf_file):
    data_list = []
    pdf_file.seek(0)
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # We check the first page for the main totals
            page = pdf.pages[0]
            text = page.extract_text()
            if not text:
                return []

            # 1. EXTRACT DATE: Matches "01.01.2019-31.01.2019" [cite: 19, 113, 213]
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})-\d{2}\.\d{2}\.\d{4}', text)
            if not date_match:
                return []
            
            raw_date = date_match.group(1)
            dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
            
            # 2. EXTRACT kWh: Specifically looks for "Kegunaan kWh" in the industrial table [cite: 16, 109, 211, 310]
            kwh_val = 0.0
            kwh_match = re.search(r'Kegunaan\s*kWh\s*kWh\s*([\d,]+\.\d{2})', text)
            if kwh_match:
                kwh_val = float(kwh_match.group(1).replace(',', ''))

            # 3. EXTRACT RM: Targets "Jumlah Bil" or "Jumlah Perlu Bayar" [cite: 6, 9, 103, 106, 201]
            rm_val = 0.0
            # Matches "Jumlah Bil RM 521,089.55" or "Jumlah Perlu Bayar RM 521,089.55"
            rm_match = re.search(r'(?:Jumlah\s*Bil|Jumlah\s*Perlu\s*Bayar)\s*(?::|RM)?\s*RM?\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
            
            if rm_match:
                rm_val = float(rm_match.group(1).replace(',', ''))
            else:
                # Fallback for "Caj Semasa" [cite: 9, 32, 110, 210]
                rm_match_alt = re.search(r'Caj\s*Semasa\s*RM\s*([\d,]+\.\d{2})', text)
                if rm_match_alt:
                    rm_val = float(rm_match_alt.group(1).replace(',', ''))

            if kwh_val > 0 or rm_val > 0:
                data_list.append({
                    "Year": dt_obj.year,
                    "Month": dt_obj.strftime("%b"),
                    "Month_Num": dt_obj.month,
                    "kWh": kwh_val,
                    "RM": rm_val
                })
                    
    except Exception as e:
        st.error(f"Error processing file: {e}")
                
    return data_list

# --- STREAMLIT UI ---
st.title("⚡ TNB Industrial Data Extractor")
st.info("Tailored for Panasonic Automotive Systems (Tarif E2) Bills")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_tnb_data(f)
        if extracted:
            all_data.extend(extracted)
    
    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month'])
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # --- DATA TABLES ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Usage (kWh)")
            kwh_pivot = df.pivot(index='Month', columns='Year', values='kWh').reindex(month_order)
            st.dataframe(kwh_pivot.style.format("{:,.2f}", na_rep="-"), use_container_width=True)
        
        with col2:
            st.subheader("Cost (RM)")
            rm_pivot = df.pivot(index='Month', columns='Year', values='RM').reindex(month_order)
            st.dataframe(rm_pivot.style.format("{:,.2f}", na_rep="-"), use_container_width=True)
        
        # --- EXCEL DOWNLOAD ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            kwh_pivot.to_excel(writer, sheet_name='kWh_Usage')
            rm_pivot.to_excel(writer, sheet_name='RM_Cost')
            # Adding a raw data sheet for better auditing
            df.sort_values(['Year', 'Month_Num']).to_excel(writer, sheet_name='Raw_Data', index=False)
        
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Consolidated_Report.xlsx")
    else:
        st.error("Still no data found. Please ensure the PDF is a digital copy and not a scanned image.")

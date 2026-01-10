import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Data Extractor", layout="wide")

def extract_tnb_data(pdf_file):
    data_list = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # 1. EXTRACT MONTH & YEAR (from 'Tempoh Bill')
            # Targeted search in the blue-shaded box area
            text = page.extract_text()
            # Look for the start date of the period (e.g., 01.01.2019)
            date_match = re.search(r'Tempoh\s*Bill\s*:\s*(\d{2}\.\d{2}\.\d{4})', text)
            
            if not date_match:
                continue
                
            raw_date = date_match.group(1)
            dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
            year = dt_obj.year
            month_name = dt_obj.strftime("%b")
            month_num = dt_obj.month

            # 2. EXTRACT kWh & RM (using Table Extraction)
            # TNB bills have clear horizontal lines. We find the table rows.
            tables = page.extract_tables()
            kwh_val = 0.0
            rm_val = 0.0
            
            for table in tables:
                for row in table:
                    # Clean the row to remove None values
                    row = [str(item) for item in row if item is not None]
                    row_text = " ".join(row)
                    
                    # Target kWh: Row starting with 'Kegunaan kWh', take last column 'Jumlah'
                    if "Kegunaan kWh" in row_text:
                        # Find the number in the last position of the row
                        nums = re.findall(r'[\d,]+\.\d{2}', row_text)
                        if nums:
                            kwh_val = float(nums[-1].replace(',', ''))
                    
            # 3. Target TOTAL RM: Usually found at the very bottom right after 'Caj Semasa'
            # We search specifically for the 'Caj Semasa' text that is followed by the total
            rm_match = re.search(r'Caj\s*Semasa\s*RM\s*([\d,]+\.\d{2})', text)
            if rm_match:
                rm_val = float(rm_match.group(1).replace(',', ''))

            if kwh_val > 0 or rm_val > 0:
                data_list.append({
                    "Year": year,
                    "Month": month_name,
                    "Month_Num": month_num,
                    "kWh": kwh_val,
                    "RM": rm_val
                })
                
    return data_list

# --- STREAMLIT UI ---
st.title("⚡ TNB Analytics Dashboard")
st.markdown("Upload your monthly bills to generate the multi-year comparison.")

uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_tnb_data(f)
        all_data.extend(extracted)
    
    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month'])
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # --- PIVOT TABLE: kWh ---
        st.subheader("Summary Comparison Electricity Usage (kWh)")
        kwh_pivot = df.pivot(index='Month', columns='Year', values='kWh').reindex(month_order)
        st.dataframe(kwh_pivot.style.format("{:,.2f} kWh", na_rep="-"), use_container_width=True)
        
        # --- PIVOT TABLE: RM ---
        st.subheader("Summary Comparison Electricity Cost (RM)")
        rm_pivot = df.pivot(index='Month', columns='Year', values='RM').reindex(month_order)
        st.dataframe(rm_pivot.style.format("RM {:,.2f}", na_rep="-"), use_container_width=True)
        
        # Excel Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            kwh_pivot.to_excel(writer, sheet_name='kWh_Comparison')
            rm_pivot.to_excel(writer, sheet_name='RM_Comparison')
        
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Summary_Report.xlsx")

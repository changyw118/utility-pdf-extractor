import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Industrial Table Extractor", layout="wide")

def extract_tnb_data(pdf_file):
    data_list = []
    pdf_file.seek(0)
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Page 1 usually contains the Bill Date and Total Amount
            first_page = pdf.pages[0]
            tables = first_page.extract_tables()
            text = first_page.extract_text()

            # 1. EXTRACT DATE (From Text)
            # Looks for "01.01.2019-31.01.2019" pattern
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})-\d{2}\.\d{2}\.\d{4}', text)
            if not date_match:
                return []
            
            raw_date = date_match.group(1)
            dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
            
            current_kwh = 0.0
            current_rm = 0.0

            # 2. EXTRACT FROM TABLES
            # We iterate through all tables found on the page
            for table in tables:
                for row in table:
                    # Clean the row (remove None and extra spaces)
                    clean_row = [str(cell).replace('\n', ' ').strip() for cell in row if cell]
                    row_str = " ".join(clean_row)

                    # Target: Kegunaan kWh (Usage)
                    if "Kegunaan kWh" in row_str:
                        # Extract the numbers from this specific row
                        nums = re.findall(r'[\d,]+\.\d{2}', row_str)
                        if nums:
                            current_kwh = float(nums[-1].replace(',', ''))

                    # Target: Caj Semasa or Jumlah Bil (Cost)
                    if "Caj Semasa" in row_str or "Jumlah Bil" in row_str:
                        rm_nums = re.findall(r'[\d,]+\.\d{2}', row_str)
                        if rm_nums:
                            current_rm = float(rm_nums[-1].replace(',', ''))

            # Fallback if Table extraction missed RM but it exists in text
            if current_rm == 0:
                rm_match = re.search(r'Jumlah\s*Perlu\s*Bayar\s*RM\s*([\d,]+\.\d{2})', text)
                if rm_match:
                    current_rm = float(rm_match.group(1).replace(',', ''))

            if current_kwh > 0 or current_rm > 0:
                data_list.append({
                    "Year": dt_obj.year,
                    "Month": dt_obj.strftime("%b"),
                    "Month_Num": dt_obj.month,
                    "kWh": current_kwh,
                    "RM": current_rm
                })
                    
    except Exception as e:
        st.error(f"Error processing file: {e}")
                
    return data_list

# --- STREAMLIT UI ---
st.title("⚡ TNB Industrial Table Extractor")
st.markdown("This version extracts data directly from the **PDF Tables** for higher accuracy.")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = extract_tnb_data(f)
        if data:
            all_results.extend(data)
    
    if all_results:
        df = pd.DataFrame(all_results).drop_duplicates(subset=['Year', 'Month'])
        df = df.sort_values(['Year', 'Month_Num'])
        
        st.subheader("Extracted Data")
        st.dataframe(df[['Year', 'Month', 'kWh', 'RM']], use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='TNB_Summary')
        
        st.download_button("📥 Save to Excel", output.getvalue(), "TNB_Data_Export.xlsx")
    else:
        st.error("Still no data. This suggests the PDF might be an 'Image PDF' or has a custom font encoding that blocks extraction.")

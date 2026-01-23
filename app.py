import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Config ---
st.set_page_config(page_title="TNB Industrial Extractor", layout="wide")

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Lowering DPI to 150 for the initial "Safe Run"
        images = convert_from_bytes(file_bytes, dpi=150) 
        total_pages = len(images)
        
        my_bar = st.progress(0)

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # Using basic config to ensure no startup errors
            text = pytesseract.image_to_string(image, lang="eng")
            
            # --- 1. DATE SEARCH (Tempoh Bil) ---
            tempoh_pattern = r'Tempoh\s*Bil.*?[\d./-]+\s*-\s*(\d{2}[./-]\d{2}[./-]\d{4})'
            date_match = re.search(tempoh_pattern, text, re.IGNORECASE | re.DOTALL)
            
            if not date_match:
                date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            if date_match:
                date_str = date_match.group(1).replace('-', '.').replace('/', '.')
                dt_obj = datetime.strptime(date_str, "%d.%m.%Y")
                
                # --- 2. kWh EXTRACTION (Large Number Fix) ---
                kwh_val = 0.0
                kwh_line_pattern = r'Kegunaan\s*(?:kWh|KWH).*?([\d\s,]+\.\d{2})'
                kwh_match = re.search(kwh_line_pattern, text, re.IGNORECASE | re.DOTALL)
                
                if kwh_match:
                    raw_val = kwh_match.group(1)
                    clean_val = "".join(c for c in raw_val if c.isdigit() or c == '.')
                    if clean_val:
                        kwh_val = float(clean_val)

                # --- 3. RM EXTRACTION (Final Total) ---
                rm_val = 0.0
                rm_pattern = r'(?:Jumlah|Caj|Total).*?(?:Perlu|Bayar|Bil|Semasa).*?(?:RM|RN|BM)?\s*([\d\s,]+\.\d{2})'
                rm_matches = list(re.finditer(rm_pattern, text, re.IGNORECASE | re.DOTALL))
                
                if rm_matches:
                    raw_rm = rm_matches[-1].group(1)
                    clean_rm = "".join(c for c in raw_rm if c.isdigit() or c == '.')
                    if clean_rm:
                        rm_val = float(clean_rm)

                if kwh_val > 0 or rm_val > 0:
                    data_list.append({
                        "Year": dt_obj.year,
                        "Month": dt_obj.strftime("%b"),
                        "Month_Num": dt_obj.month,
                        "kWh": kwh_val,
                        "RM": rm_val
                    })
            
            image.close()
            
        my_bar.empty()
    except Exception as e:
        st.error(f"Error: {e}")
    return data_list

# --- User Interface ---
st.title("⚡ TNB Industrial Smart Extractor")
uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = extract_data_with_ocr(f)
        if data:
            all_results.extend(data)
    
    if all_results:
        df = pd.DataFrame(all_results).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        # Excel Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "TNB_Report.xlsx")

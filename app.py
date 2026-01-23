import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Universal Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """
    Ensures million-scale numbers are captured correctly by removing all 
    non-numeric characters except the final decimal point.
    """
    if not raw_str: return 0.0
    # Remove everything except digits and the decimal point
    clean = "".join(c for c in raw_str if c.isdigit() or c == '.')
    
    # If multiple dots appear due to OCR errors, keep only the last one
    if clean.count('.') > 1:
        parts = clean.split('.')
        clean = "".join(parts[:-1]) + "." + parts[-1]
        
    try:
        return float(clean)
    except:
        return 0.0

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # 200 DPI is recommended for industrial bills to distinguish commas from dots
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 is vital for keeping large numbers on a single horizontal line
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. FLEXIBLE DATE SEARCH ---
            dt_obj = None
            tempoh_pattern = r'Tempoh\s*Bil.*?[\d./-]+\s*-\s*(\d{2}[./-]\d{2}[./-]\d{4})'
            date_match = re.search(tempoh_pattern, text, re.IGNORECASE | re.DOTALL)
            
            if not date_match:
                date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            if date_match:
                raw_date = date_match.group(1).replace('-', '.').replace('/', '.')
                day_part = raw_date[:2]
                if day_part.startswith('9'): raw_date = '3' + raw_date[1:] 
                
                try:
                    dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except ValueError:
                    continue 

                # --- 2. FORCED kWh EXTRACTION (The Fix) ---
                kwh_val = 0.0
                # This pattern captures a wider range of characters to prevent truncation
                kwh_pattern = r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})'
                kwh_match = re.search(kwh_pattern, text, re.IGNORECASE | re.DOTALL)
                if kwh_match:
                    kwh_val = clean_industrial_num(kwh_match.group(1))

                # --- 3. FORCED RM EXTRACTION ---
                rm_val = 0.0
                rm_pattern = r'(?:Jumlah|Caj|Total).*?(?:Perlu|Bayar|Bil|Semasa).*?(?:RM|RN|BM)?\s*([\d\s,.]+\d{2})'
                rm_matches = list(re.finditer(rm_pattern, text, re.IGNORECASE | re.DOTALL))
                if rm_matches:
                    rm_val = clean_industrial_num(rm_matches[-1].group(1))

                if kwh_val > 0 or rm_val > 0:
                    data_list.append({
                        "Year": dt_obj.year,
                        "Month": dt_obj.strftime("%b"),
                        "Month_Num": dt_obj.month,
                        "kWh": kwh_val,
                        "RM": rm_val
                    })
            
            image.close() 
            del image
            gc.collect() 
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ App Error: {e}")
    return data_list

# --- UI ---
st.title("⚡ TNB Universal Smart Extractor")
uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = extract_data_with_ocr(f)
        if data: all_results.extend(data)
    
    if all_results:
        df = pd.DataFrame(all_results).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        st.subheader("📊 Extracted Summary")
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Report.xlsx")

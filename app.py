import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Configuration ---
st.set_page_config(page_title="TNB Universal Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """
    Collapses '1,364,751.00' into '1364751.00' to prevent digit loss.
    """
    if not raw_str: return 0.0
    clean = "".join(c for c in raw_str if c.isdigit() or c == '.')
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
        
        # 200 DPI for high precision.
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 keeps the layout structured.
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. STRICT POSITIONAL DATE SEARCH ---
            dt_obj = None
            # We look specifically for the line starting with 'Tempoh Bil' 
            # and grab the FIRST date (e.g., 01.01.2020).
            tempoh_line = re.search(r'Tempoh\s*Bil.*?:?\s*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
            
            if tempoh_line:
                raw_date = tempoh_line.group(1).replace('-', '.').replace('/', '.')
            else:
                # Tier 2: Only if 'Tempoh Bil' is not found, look for dates between 
                # 'Tarikh Bil' and 'No. Invois'.
                section = re.search(r'Tarikh\s*Bil(.*?)No\.\s*Invois', text, re.IGNORECASE | re.DOTALL)
                if section:
                    dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', section.group(1))
                    # Usually the second date in this box is the Start Date.
                    raw_date = dates[1].replace('-', '.').replace('/', '.') if len(dates) > 1 else None
                else:
                    raw_date = None
            
            if raw_date:
                # OCR typo correction.
                if raw_date[:2].startswith('9'): raw_date = '3' + raw_date[1:] 
                try:
                    dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except: pass

            if dt_obj and 2010 <= dt_obj.year <= 2030:
                # --- 2. LARGE kWh EXTRACTION (Million Fix) ---
                # Anchored to 'Kegunaan kWh'.
                kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                kwh_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0

                # --- 3. RM EXTRACTION ---
                # Anchored to 'Jumlah Perlu Bayar'.
                rm_match = re.search(r'Jumlah\s*Perlu\s*Bayar.*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                if not rm_match:
                    backup = list(re.finditer(r'(?:Jumlah|Total|Caj).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL))
                    rm_val = clean_industrial_num(backup[-1].group(1)) if backup else 0.0
                else:
                    rm_val = clean_industrial_num(rm_match.group(1))

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
        st.error(f"⚠️ Extraction Error: {e}")
    return data_list

# --- UI ---
st.title("⚡ TNB Industrial Smart Extractor")
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

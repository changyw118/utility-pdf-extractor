import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Configuration ---
st.set_page_config(page_title="TNB Precise Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """Collapses million-scale numbers to prevent digit loss."""
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
        
        # 250 DPI for deep clarity to distinguish dates.
        images = convert_from_bytes(file_bytes, dpi=250, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 keeps table rows and header boxes aligned.
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. THE POSITIONAL DATE LOCK ---
            dt_obj = None
            
            # We look for 'Tempoh Bil' and take the FIRST date that appears before the hyphen.
            # This targets 01.01.2020 specifically.
            date_anchor = re.search(r'Tempoh\s*Bil.*?:?\s*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
            
            if date_anchor:
                raw_date = date_anchor.group(1).replace('-', '.').replace('/', '.')
                # Correct common OCR day misreads (e.g. 90 -> 30).
                if raw_date.startswith('9'): raw_date = '3' + raw_date[1:]
                
                try:
                    dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except:
                    pass

            # --- 2. MULTI-LEVEL VALUE SEARCH ---
            if dt_obj and 2010 <= dt_obj.year <= 2030:
                # Capture kWh - prevents truncation of 1,364,751.00.
                kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                kwh_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0

                # Capture RM - Anchored to "Jumlah Perlu Bayar".
                rm_match = re.search(r'Jumlah\s*Perlu\s*Bayar.*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                if not rm_match:
                    backup = list(re.finditer(r'(?:RM|RN|BM)?\s*([\d\s,.]+\d{2})', text, re.IGNORECASE))
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
        st.error(f"⚠️ Technical Alert: {e}")
    return data_list

# --- UI & EXCEL FORMATTING ---
st.title("⚡ TNB Absolute Precision Extractor")
uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = extract_data_with_ocr(f)
        if data: all_results.extend(data)
    
    if all_results:
        # Deduplicate and sort chronologically.
        df = pd.DataFrame(all_results).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        
        st.subheader("📊 Extracted Summary")
        # Format the table display with commas and 2 decimals.
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[['Year', 'Month', 'kWh', 'RM']].to_excel(writer, index=False, sheet_name='TNB_Data')
            workbook  = writer.book
            worksheet = writer.sheets['TNB_Data']
            # Force industrial #,##0.00 format in the downloaded file.
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            worksheet.set_column('C:D', 20, num_format)
            
        st.download_button("📥 Download Formatted Excel Report", output.getvalue(), "TNB_Report.xlsx")

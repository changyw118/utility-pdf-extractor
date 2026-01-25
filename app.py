import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Configuration ---
st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """Collapses '1,364,751.00' into '1364751.00' to prevent digit loss."""
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
        
        # 200 DPI is required for small industrial font clarity.
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 maintains table structure for large numbers.
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. PRECISE DATE EXTRACTION (The 3-Date Fix) ---
            dt_obj = None
            # We isolate the specific header box.
            header_section = re.search(r'Tarikh\s*Bil(.*?)No\.\s*Invois', text, re.IGNORECASE | re.DOTALL)
            
            if header_section:
                dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', header_section.group(1))
                # According to your bill layout, the second date is the Start Date.
                if len(dates) >= 2:
                    raw_date = dates[1].replace('-', '.').replace('/', '.')
                    # OCR '90' day fix.
                    if raw_date.startswith('9'): raw_date = '3' + raw_date[1:]
                    try:
                        dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                    except: pass
            
            # --- 2. FORCED kWh & RM EXTRACTION (Million Digit Fix) ---
            if dt_obj and 2010 <= dt_obj.year <= 2030:
                # kWh search.
                kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                kwh_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0

                # RM search.
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
        st.error(f"⚠️ App Error: {e}")
    return data_list

# --- UI & Excel Export ---
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
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[['Year', 'Month', 'kWh', 'RM']].to_excel(writer, index=False, sheet_name='TNB_Data')
            workbook  = writer.book
            worksheet = writer.sheets['TNB_Data']
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            worksheet.set_column('C:D', 20, num_format) # Apply industrial format.
            
        st.download_button("📥 Download Formatted Excel Report", output.getvalue(), "TNB_Precise_Report.xlsx")

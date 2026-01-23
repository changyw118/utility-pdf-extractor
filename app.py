import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Row-Anchor Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """Collapses spaces and commas to prevent digit loss in million-scale numbers."""
    if not raw_str: return 0.0
    # Remove everything except digits and the decimal point.
    clean = "".join(c for c in raw_str if c.isdigit() or c == '.')
    # If OCR sees two dots, keep only the last one as the decimal.
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
        # 200 DPI is standard for balancing memory and precision.
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")
        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / len(images)) * 100))
            
            # PSM 6 forces Tesseract to read line-by-line.
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            lines = text.split('\n')
            
            page_date, page_kwh, page_rm = None, 0.0, 0.0
            
            for line in lines:
                # --- 1. DATE: Find 'Tempoh Bil' line and take the 1st date ---
                if "Tempoh Bil" in line:
                    dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', line)
                    if dates:
                        raw_date = dates[0].replace('-', '.').replace('/', '.')
                        if raw_date.startswith('9'): raw_date = '3' + raw_date[1:] # Fix '90' error.
                        try:
                            page_date = datetime.strptime(raw_date, "%d.%m.%Y")
                        except: pass

                # --- 2. kWh: Find 'Kegunaan' line and take the large number ---
                if "Kegunaan" in line and ("kWh" in line or "KWH" in line):
                    # Finds the number with 2 decimal places at the end of the line.
                    val_match = re.search(r'([\d\s,.]+\.\d{2})', line)
                    if val_match:
                        page_kwh = clean_industrial_num(val_match.group(1))

                # --- 3. RM: Find 'Jumlah Perlu Bayar' line ---
                if "Jumlah Perlu Bayar" in line or "Perlu Bayar" in line:
                    val_match = re.search(r'([\d\s,.]+\.\d{2})', line)
                    if val_match:
                        page_rm = clean_industrial_num(val_match.group(1))

            if page_date and (page_kwh > 0 or page_rm > 0):
                data_list.append({
                    "Year": page_date.year,
                    "Month": page_date.strftime("%b"),
                    "Month_Num": page_date.month,
                    "kWh": page_kwh,
                    "RM": page_rm
                })
            
            image.close()
            del image
            gc.collect() 
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ App Error: {e}")
    return data_list

# --- UI & Excel Format ---
st.title("⚡ TNB Absolute Precision Extractor")
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
            workbook, worksheet = writer.book, writer.sheets['TNB_Data']
            num_format = workbook.add_format({'num_format': '#,##0.00'})
            worksheet.set_column('C:D', 20, num_format) # Forces comma format in Excel.
            
        st.download_button("📥 Download Formatted Excel Report", output.getvalue(), "TNB_Final_Report.xlsx")

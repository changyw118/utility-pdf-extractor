import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

# ==========================================
# ⚙️ CONFIGURATION - UPDATE THESE PATHS
# ==========================================
# 1. Update this to your Tesseract EXE location

# 2. Update this to your Poppler BIN folder location
# ==========================================

st.set_page_config(page_title="TNB Smart OCR Extractor", layout="wide")

def extract_data_with_ocr(pdf_file):
    data_list = []
    pdf_file.seek(0)
    file_bytes = pdf_file.read()
    
    try:
        # Step A: Convert ALL pages to images for OCR
        # Removing first_page and last_page makes it process the whole document
        st.info("🔄 Processing all pages... please wait.")
        images = convert_from_bytes(file_bytes) 
        
        # Step B: Loop through every single page
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image)
            
            # Step C: Parse the data for THIS specific page
            # 1. Date
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
            if not date_match:
                continue # Skip this page if no date is found
                
            dt_obj = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            
            # 2. kWh Usage
            kwh_val = 0.0
            kwh_match = re.search(r'Kegunaan\s*kWh.*?([\d,]+\.\d{2})', text, re.DOTALL)
            if kwh_match:
                kwh_val = float(kwh_match.group(1).replace(',', ''))

            # 3. Total RM Cost
            rm_val = 0.0
            rm_match = re.search(r'(?:Jumlah\s*Perlu\s*Bayar|Jumlah\s*Bil|Caj\s*Semasa)\s*RM\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
            if rm_match:
                rm_val = float(rm_match.group(1).replace(',', ''))

            # Only add to list if we found actual values on this page
            if kwh_val > 0 or rm_val > 0:
                data_list.append({
                    "Year": dt_obj.year,
                    "Month": dt_obj.strftime("%b"),
                    "Month_Num": dt_obj.month,
                    "kWh": kwh_val,
                    "RM": rm_val,
                    "Page": i + 1  # Optional: keeps track of which page it came from
                })
                    
    except Exception as e:
        st.error(f"⚠️ OCR Error: {e}. Ensure packages.txt is present.")
                
    return data_list
    
# --- UI ---
st.title("⚡ TNB Industrial Smart Extractor")
st.markdown("Upload your Panasonic Automotive Systems PDFs (Scanned or Digital).")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_data_with_ocr(f)
        if extracted:
            all_data.extend(extracted)
    
    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        st.subheader("📊 Extracted Summary")
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        # Excel Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='TNB_Analytics')
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Consolidated_Report.xlsx")
    else:
        st.warning("No data found. Check if the PDF is clearly readable.")

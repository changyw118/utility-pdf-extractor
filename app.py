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
        # Step A: Try normal digital text extraction
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "")
            
        # Step B: If text is missing or unreadable, use the OCR tools you downloaded
        if "Kegunaan" not in text:
            st.info("🔄 Scanned PDF detected. Running OCR scan...")
            images = convert_from_bytes(file_bytes, first_page=1, last_page=1)
            if images:
                text = pytesseract.image_to_string(images[0])
        
        # Step C: Parse the data found in your Panasonic bills
        # 1. Date (e.g., 01.01.2019) [cite: 19, 113, 213]
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
        if not date_match: return []
        dt_obj = datetime.strptime(date_match.group(1), "%d.%m.%Y")
        
        # 2. kWh Usage (e.g., 1,360,581.00) 
        kwh_val = 0.0
        kwh_match = re.search(r'Kegunaan\s*kWh.*?([\d,]+\.\d{2})', text, re.DOTALL)
        if kwh_match:
            kwh_val = float(kwh_match.group(1).replace(',', ''))

        # 3. Total RM Cost (e.g., 521,089.55) [cite: 6, 9, 32, 103, 106, 127]
        rm_val = 0.0
        rm_match = re.search(r'(?:Jumlah\s*Perlu\s*Bayar|Jumlah\s*Bil|Caj\s*Semasa)\s*RM\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
        if rm_match:
            rm_val = float(rm_match.group(1).replace(',', ''))

        if kwh_val > 0 or rm_val > 0:
            data_list.append({
                "Year": dt_obj.year,
                "Month": dt_obj.strftime("%b"),
                "Month_Num": dt_obj.month,
                "kWh": kwh_val,
                "RM": rm_val
            })
                    
    except Exception as e:
        st.error(f"⚠️ OCR Error: {e}. Please check your Tesseract and Poppler paths.")
                
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

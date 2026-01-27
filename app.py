import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

# --- SIDEBAR SETUP ---
st.sidebar.header("🔧 Windows Configuration")

# Set these default paths to match your current setup
default_poppler = r"C:\poppler\Library\bin"
default_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

poppler_path = st.sidebar.text_input("Poppler Bin Path", value=default_poppler)
tesseract_exe = st.sidebar.text_input("Tesseract EXE Path", value=default_tesseract)

# --- HELPER FUNCTIONS ---
def clean_num(raw_str):
    if not raw_str: return 0.0
    clean = re.sub(r'[^\d.]', '', raw_str.replace(' ', '').replace(',', ''))
    try:
        return float(clean)
    except:
        return 0.0

def process_bill(pdf_file, p_path, t_path):
    data_list = []
    
    # 1. Setup Tesseract Path
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
    else:
        st.error(f"❌ Tesseract not found at: {t_path}")
        return None

    # 2. Main Processing Block
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Convert PDF to Images
        # We wrap this in another try to catch Poppler-specific path errors
        try:
            images = convert_from_bytes(
                file_bytes, 
                dpi=150, 
                poppler_path=p_path if p_path else None
            )
        except Exception as pe:
            st.error(f"❌ Poppler Error: {pe}")
            st.info(f"Check if pdfinfo.exe exists in: {p_path}")
            return None

        st.success(f"✅ Successfully loaded {len(images)} pages!")
        
        # 3. OCR Scan
        progress_bar = st.progress(0)
        for i, img in enumerate(images):
            progress_bar.progress((i + 1) / len(images), text=f"Scanning Page {i+1}...")
            
            # Pre-process for better OCR
            img = ImageOps.grayscale(img)
            text = pytesseract.image_to_string(img, lang="eng")
            
            # 4. Regex Extraction (Searching for Date, kWh, and RM)
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            kwh_match = re.search(r'(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match and (kwh_match or rm_match):
                data_list.append({
                    "Billing Date": date_match.group(1),
                    "kWh Usage": clean_num(kwh_match.group(1)) if kwh_match else 0.0,
                    "Total Amount (RM)": clean_num(rm_match.group(1)) if rm_match else 0.0,
                    "Source Page": i + 1
                })
            
            # Memory Cleanup
            del img
            gc.collect()

        progress_bar.empty()
        return data_list

    except Exception as e:
        st.error(f"❌ Critical Error: {str(e)}")
        return None

# --- UI LAYOUT ---
st.title("⚡ TNB Industrial Bill Data Extractor")
st.write("Upload scanned PDFs to extract billing data into Excel.")

uploaded_files = st.file_uploader("Upload TNB Bills (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 Start Extraction"):
        all_results = []
        for f in uploaded_files:
            res = process_bill(f, poppler_path, tesseract_exe)
            if res:
                all_results.extend(res)
        
        if all_results:
            df = pd.DataFrame(all_results)
            st.subheader("📊 Extracted Data")
            # Editable table for manual correction
            edited_df = st.data_editor(df, use_container_width=True)
            
            # Excel Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Download as Excel",
                data=buffer.getvalue(),
                file_name=f"TNB_Export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.warning("No valid data found in the uploaded bills.")

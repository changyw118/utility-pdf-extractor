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
import platform

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

# --- SMART PATH CONFIGURATION ---
def setup_paths():
    # Detect if we are on Windows or Linux (Cloud)
    is_windows = platform.system() == "Windows"
    
    if is_windows:
        st.sidebar.header("🔧 Windows Configuration")
        # You can change these defaults to your local paths
        default_pop = r"C:\poppler\Library\bin"
        default_tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        
        p_path = st.sidebar.text_input("Poppler Bin Path", value=default_pop)
        t_path = st.sidebar.text_input("Tesseract EXE Path", value=default_tess)
        
        if os.path.exists(t_path):
            pytesseract.pytesseract.tesseract_cmd = t_path
    else:
        # Linux (Streamlit Cloud) configuration
        # On Linux, these are usually in the system PATH automatically
        p_path = None 
        t_path = "tesseract" 
        # No need to set pytesseract.tesseract_cmd on Linux if installed via packages.txt
        
    return p_path, t_path

poppler_path, tesseract_path = setup_paths()

# --- HELPER FUNCTIONS ---
def clean_num(raw_str):
    if not raw_str: return 0.0
    clean = re.sub(r'[^\d.]', '', raw_str.replace(' ', '').replace(',', ''))
    try:
        return float(clean)
    except:
        return 0.0

def process_bill(pdf_file, p_path):
    data_list = []
    
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Convert PDF to Images
        images = convert_from_bytes(
            file_bytes, 
            dpi=150, 
            poppler_path=p_path if p_path and os.path.exists(p_path) else None
        )

        st.success(f"✅ Successfully loaded {len(images)} pages!")
        
        progress_bar = st.progress(0)
        for i, img in enumerate(images):
            progress_bar.progress((i + 1) / len(images), text=f"Scanning Page {i+1}...")
            
            # Pre-process for better OCR
            img = ImageOps.grayscale(img)
            text = pytesseract.image_to_string(img, lang="eng")
            
            # --- EXTRACTION LOGIC ---
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            kwh_match = re.search(r'(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match:
                data_list.append({
                    "Billing Date": date_match.group(1),
                    "kWh Usage": clean_num(kwh_match.group(1)) if kwh_match else 0.0,
                    "Total Amount (RM)": clean_num(rm_match.group(1)) if rm_match else 0.0,
                    "Source Page": i + 1
                })
            
            del img
            gc.collect()

        progress_bar.empty()
        return data_list

    except Exception as e:
        st.error(f"❌ Processing Error: {str(e)}")
        return None

# --- UI LAYOUT ---
st.title("⚡ TNB Industrial Bill Data Extractor")
st.write("Upload scanned PDFs to extract billing data into Excel.")

uploaded_files = st.file_uploader("Upload TNB Bills (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 Start Extraction"):
        all_results = []
        for f in uploaded_files:
            res = process_bill(f, poppler_path)
            if res:
                all_results.extend(res)
        
        if all_results:
            df = pd.DataFrame(all_results)
            st.subheader("📊 Extracted Data")
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
            st.warning("No valid data found. Check if the OCR can read the text clearly.")

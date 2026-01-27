import streamlit as st
import pandas as pd
import re
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
import os
import platform

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Bill Extractor", layout="wide")

# --- SYSTEM DETECTION ---
IS_CLOUD = platform.system() == "Linux"

def setup_environment():
    p_path = None
    if not IS_CLOUD:
        st.sidebar.header("🔧 Local Windows Settings")
        # Change these to your local paths if testing on your PC
        p_path = st.sidebar.text_input("Poppler Bin Path", value=r"C:\poppler\Library\bin")
        t_path = st.sidebar.text_input("Tesseract EXE Path", value=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        
        if os.path.exists(t_path):
            pytesseract.pytesseract.tesseract_cmd = t_path
    else:
        st.sidebar.success("☁️ Running on Streamlit Cloud")
        st.sidebar.info("System dependencies managed by packages.txt")
    return p_path

poppler_bin = setup_environment()

# --- EXTRACTION LOGIC ---
def extract_tnb_data(pdf_file, p_path):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Convert PDF to Images
        images = convert_from_bytes(
            file_bytes, 
            dpi=150, 
            poppler_path=p_path
        )
        
        st.info(f"Processing {len(images)} pages...")
        
        progress_bar = st.progress(0)
        for i, img in enumerate(images):
            progress_bar.progress((i + 1) / len(images))
            
            # OCR with Grayscale for better accuracy
            text = pytesseract.image_to_string(ImageOps.grayscale(img))
            
            # Regex Patterns for TNB Bills
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            kwh_match = re.search(r'(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match or rm_match:
                data_list.append({
                    "Billing Date": date_match.group(1) if date_match else "N/A",
                    "kWh Usage": kwh_match.group(1).replace(' ', '') if kwh_match else "0.00",
                    "Total RM": rm_match.group(1).replace(' ', '') if rm_match else "0.00",
                    "Page": i + 1
                })
            
            del img
            gc.collect()
        
        progress_bar.empty()
        return data_list

    except Exception as e:
        st.error(f"❌ Extraction Error: {e}")
        return None

# --- UI ---
st.title("⚡ TNB Industrial PDF Extractor")
st.write("Upload your TNB bill PDF to extract usage and cost data.")

uploaded_file = st.file_uploader("Upload PDF", type="pdf")

if uploaded_file:
    if st.button("Extract Data"):
        results = extract_tnb_data(uploaded_file, poppler_bin)
        
        if results:
            df = pd.DataFrame(results)
            st.subheader("Results")
            # Editable table for manual double-check
            edited_df = st.data_editor(df, use_container_width=True)
            
            # Export to Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Download as Excel",
                data=output.getvalue(),
                file_name="TNB_Extracted.xlsx",
                mime="application/vnd.ms-excel"
            )

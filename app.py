import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
from pathlib import Path
import os

st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("🔧 Windows Setup")
# Paste your path here: C:\poppler\poppler-25.12.0\Library\bin
poppler_input = st.sidebar.text_input("1. Poppler Bin Path", value=r"C:\poppler\poppler-25.12.0\Library\bin")
tesseract_input = st.sidebar.text_input("2. Tesseract EXE Path", value=r"C:\Program Files\Tesseract-OCR\tesseract.exe")

def extract_data_with_ocr(pdf_file):
    data_list = []
    
    # Clean paths
    p_path = poppler_input.strip().replace('"', '')
    t_path = tesseract_input.strip().replace('"', '')
    
    if t_path:
        pytesseract.pytesseract.tesseract_cmd = t_path

    try:
        # Check if Poppler path actually exists
        if not os.path.exists(p_path):
            st.error(f"❌ The Poppler path does not exist: {p_path}")
            return []

        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # --- CONVERT PDF TO IMAGES ---
        images = convert_from_bytes(
            file_bytes, 
            dpi=150, 
            poppler_path=p_path
        )
        
        st.success(f"✅ Successfully loaded {len(images)} pages!")
        
        my_bar = st.progress(0, text="OCR Scanning in progress...")
        for i, image in enumerate(images):
            my_bar.progress((i + 1) / len(images))
            
            # Convert to grayscale for better OCR
            text = pytesseract.image_to_string(ImageOps.grayscale(image), lang="eng")
            
            # --- EXTRACTION LOGIC ---
            # Date Search
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            # kWh Search (Looks for kWh followed by numbers)
            kwh_match = re.search(r'(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            # RM Search
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match:
                data_list.append({
                    "Date": date_match.group(1),
                    "kWh": kwh_match.group(1) if kwh_match else "Not Found",
                    "RM": rm_match.group(1) if rm_match else "Not Found",
                    "Page": i + 1
                })
            
            del image
            gc.collect()

        my_bar.empty()

    except Exception as e:
        st.error(f"❌ Error during processing: {e}")
        st.info("💡 Hint: Ensure 'pdfinfo.exe' is inside your Poppler Bin Path.")
        
    return data_list

# --- MAIN UI ---
st.title("⚡ TNB Industrial Bill Extractor")

uploaded_file = st.file_uploader("Upload TNB PDF", type="pdf")

if uploaded_file:
    if st.button("Extract Data Now"):
        with st.spinner("Processing..."):
            results = extract_data_with_ocr(uploaded_file)
            
            if results:
                df = pd.DataFrame(results)
                st.subheader("Extracted Results")
                st.dataframe(df, use_container_width=True)
                
                # Excel Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download as Excel",
                    data=output.getvalue(),
                    file_name="TNB_Extracted_Data.xlsx",
                    mime="application/vnd.ms-excel"
                )

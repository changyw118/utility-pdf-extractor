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

st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

st.sidebar.header("🔧 Windows Setup")
# We use os.path.normpath to fix any slash issues automatically
poppler_input = st.sidebar.text_input("1. Poppler Bin Path", placeholder=r"C:\poppler\bin")
tesseract_input = st.sidebar.text_input("2. Tesseract EXE Path", placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe")

def extract_data_with_ocr(pdf_file):
    data_list = []
    current_bill_date = None 
    
    # Clean up paths from sidebar
    p_path = os.path.normpath(poppler_input) if poppler_input else None
    t_path = os.path.normpath(tesseract_input) if tesseract_input else None
    
    if t_path:
        pytesseract.pytesseract.tesseract_cmd = t_path

    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # This is where Poppler is used
        # The 'r' before the quote is the secret sauce for Windows paths!
images = convert_from_bytes(
    file_bytes, 
    dpi=150, 
    poppler_path=r'C:\poppler-25.12.0\Library\bin'
)

        
        my_bar = st.progress(0, text="Reading PDF pages...")
        for i, image in enumerate(images):
            my_bar.progress((i + 1) / len(images))
            text = pytesseract.image_to_string(ImageOps.grayscale(image), lang="eng")
            
            # --- Extraction Logic ---
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            kwh_match = re.search(r'(?:kWh|KWH)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match and (kwh_match or rm_match):
                data_list.append({
                    "Date": date_match.group(1),
                    "kWh": kwh_match.group(1) if kwh_match else "0.00",
                    "RM": rm_match.group(1) if rm_match else "0.00",
                    "Page": i + 1
                })
        my_bar.empty()
    except Exception as e:
        st.error(f"❌ Error: {e}")
    return data_list

# UI
st.title("⚡ TNB Bill Extractor")
uploaded_file = st.file_uploader("Upload TNB PDF", type="pdf")
if uploaded_file and st.button("Start Extraction"):
    results = extract_data_with_ocr(uploaded_file)
    if results:
        st.write(pd.DataFrame(results))

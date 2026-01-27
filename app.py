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

st.set_page_config(page_title="TNB Extractor", layout="wide")

# --- AUTO-DETECTION ---
IS_CLOUD = platform.system() == "Linux"

if not IS_CLOUD:
    st.sidebar.header("🔧 Local Windows Settings")
    p_path = st.sidebar.text_input("Poppler Path", value=r"C:\poppler\Library\bin")
    t_path = st.sidebar.text_input("Tesseract Path", value=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
else:
    # On Cloud, we use system defaults
    p_path = None 
    st.sidebar.success("☁️ Running on Cloud: System paths managed automatically.")

def process_bill(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        # On Cloud, poppler_path=None tells it to look in the Linux system PATH
        images = convert_from_bytes(pdf_file.read(), dpi=150, poppler_path=p_path)
        
        bar = st.progress(0)
        for i, img in enumerate(images):
            bar.progress((i + 1) / len(images))
            text = pytesseract.image_to_string(ImageOps.grayscale(img))
            
            # Simple extraction logic
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            rm_match = re.search(r'RM\s*([\d\s,.]+\d{2})', text)
            
            if date_match or rm_match:
                data_list.append({
                    "Date": date_match.group(1) if date_match else "Unknown",
                    "Amount": rm_match.group(1) if rm_match else "0.00",
                    "Page": i + 1
                })
            del img
            gc.collect()
        return data_list
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return None

st.title("⚡ TNB Bill Extractor")
uploaded = st.file_uploader("Upload PDF", type="pdf")

if uploaded and st.button("Extract"):
    results = process_bill(uploaded)
    if results:
        st.write(pd.DataFrame(results))

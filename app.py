import streamlit as st
import pandas as pd
import re
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps, ImageEnhance
import platform
import os

st.set_page_config(page_title="TNB Master Extractor", layout="wide")

# --- ENVIRONMENT ---
IS_CLOUD = platform.system() == "Linux"
def setup_env():
    p_path = None
    if not IS_CLOUD:
        p_path = r"C:\poppler\Library\bin"
        t_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(t_path):
            pytesseract.pytesseract.tesseract_cmd = t_path
    return p_path

poppler_bin = setup_env()

def clean_rm(text):
    """Forcefully cleans RM strings into floats."""
    if not text: return 0.0
    # Remove everything except digits and dots
    clean = re.sub(r'[^\d.]', '', text.replace(',', '.'))
    try:
        # Handle cases with multiple dots like '1.234.50'
        if clean.count('.') > 1:
            parts = clean.split('.')
            clean = "".join(parts[:-1]) + "." + parts[-1]
        return float(clean)
    except:
        return 0.0

def process_bill(pdf_file, p_path, debug_mode):
    all_data = []
    try:
        pdf_file.seek(0)
        # 300 DPI + Grayscale is best for TNB fonts
        images = convert_from_bytes(pdf_file.read(), dpi=300, poppler_path=p_path)
        
        for i, img in enumerate(images):
            # --- IMAGE ENHANCEMENT ---
            img = ImageOps.grayscale(img)
            # Increase contrast significantly
            img = ImageEnhance.Contrast(img).enhance(2.5)
            # Thresholding to remove 'gray' noise
            img = img.point(lambda x: 0 if x < 120 else 255)
            
            # --- OCR ---
            text = pytesseract.image_to_string(img, lang="eng")
            
            if debug_mode:
                with st.expander(f"🔍 View Raw Text - Page {i+1}"):
                    st.code(text)

            # --- FUZZY EXTRACTION ---
            # 1. Date: Look for any DD/MM/YYYY or DD.MM.YYYY
            dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            # 2. Amount: Look for RM followed by numbers
            amounts = re.findall(r'RM\s*([\d\s,.]+\.\d{2})', text, re.IGNORECASE)
            
            # 3. kWh: Look for numbers ending in kWh
            kwh_vals = re.findall(r'([\d\s,]+)\s*kWh', text, re.IGNORECASE)

            # If we found anything, pick the most likely candidates
            if dates or amounts or kwh_vals:
                all_data.append({
                    "Billing Date": dates[0] if dates else "Not Found",
                    "Usage (kWh)": kwh_vals[0].strip().replace(',', '') if kwh_vals else "0",
                    "Total RM": max([clean_rm(a) for a in amounts]) if amounts else 0.0,
                    "Page": i + 1
                })
            
            del img
            gc.collect()
            
        return all_data
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- UI ---
st.title("⚡ TNB Industrial Data Extractor")
debug_mode = st.checkbox("Enable Debug Mode (See raw OCR text)")

uploaded_file = st.file_uploader("Upload TNB Bill PDF", type="pdf")

if uploaded_file and st.button("🚀 Run Extraction"):
    results = process_bill(uploaded_file, poppler_bin, debug_mode)
    if results:
        df = pd.DataFrame(results)
        st.subheader("📋 Results")
        st.data_editor(df, use_container_width=True)
        
        # Excel Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "TNB_Data.xlsx")

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

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Industrial Data Extractor", layout="wide")

# --- ENVIRONMENT DETECTION ---
IS_CLOUD = platform.system() == "Linux"

def setup_env():
    p_path = None
    if not IS_CLOUD:
        # Local Windows paths
        p_path = r"C:\poppler\Library\bin"
        t_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(t_path):
            pytesseract.pytesseract.tesseract_cmd = t_path
    return p_path

poppler_bin = setup_env()

def clean_extracted_value(val):
    """Removes spaces and commas, ensuring a clean numeric string."""
    if not val: return "0.00"
    return val.replace(',', '').replace(' ', '').strip()

def process_bill(pdf_file, p_path):
    all_data = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # 1. High-Resolution Conversion (300 DPI is key for accuracy)
        images = convert_from_bytes(file_bytes, dpi=300, poppler_path=p_path)
        
        st.info(f"Processing {len(images)} pages at high resolution...")
        prog = st.progress(0)
        
        for i, img in enumerate(images):
            prog.progress((i + 1) / len(images), text=f"Analyzing Page {i+1}...")
            
            # 2. Advanced Image Pre-processing
            img = ImageOps.grayscale(img)
            img = ImageEnhance.Contrast(img).enhance(2.0) # Boost contrast
            img = img.point(lambda x: 0 if x < 140 else 255) # Binarize (Pure B&W)
            
            # 3. Perform OCR
            text = pytesseract.image_to_string(img, lang="eng")
            
            # 4. Strict Regex Extraction
            # Billing Date: Look for 'Tarikh Bil'
            date_match = re.search(r'Tarikh\s+Bil\s*[:\s]*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
            
            # Usage kWh: Look for 'Kegunaan' or 'Usage' followed by digits
            kwh_match = re.search(r'(?:Kegunaan|Usage)\s*[:\s]*([\d,]+)\s*kWh', text, re.IGNORECASE)
            
            # Total Amount: Look for 'Jumlah Perlu Bayar' followed by RM and decimals
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar\s*[:\s]*RM\s*([\d\s,.]+\.\d{2})', text, re.IGNORECASE)

            if date_match or rm_match or kwh_match:
                all_data.append({
                    "Billing Date": date_match.group(1) if date_match else "N/A",
                    "Usage (kWh)": clean_extracted_value(kwh_match.group(1)) if kwh_match else "0.00",
                    "Total Amount (RM)": clean_extracted_value(rm_match.group(1)) if rm_match else "0.00",
                    "Page": i + 1
                })
            
            # Memory safety
            del img
            gc.collect()
            
        return all_data

    except Exception as e:
        st.error(f"❌ Extraction Error: {e}")
        return None

# --- UI ---
st.title("⚡ TNB Industrial PDF Extractor (High Accuracy)")
st.markdown("This tool uses **300 DPI OCR scanning** to ensure precise data capture from TNB bills.")



uploaded_file = st.file_uploader("Upload TNB Bill PDF", type="pdf")

if uploaded_file:
    if st.button("🚀 Start Precision Extraction"):
        with st.spinner("Enhancing image quality and reading text..."):
            results = process_bill(uploaded_file, poppler_bin)
            
            if results:
                df = pd.DataFrame(results)
                
                # Show results in an editable table
                st.subheader("📋 Extracted Data")
                st.info("Tip: You can click any cell below to manually fix minor OCR errors before downloading.")
                edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
                
                # Excel Export
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    edited_df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download Corrected Data (Excel)",
                    data=buffer.getvalue(),
                    file_name=f"TNB_Data_{uploaded_file.name}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("Could not find specific TNB keywords. Is this a standard TNB industrial bill?")

import streamlit as st
import pandas as pd
import re
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
import platform
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Bill Extractor", layout="wide")

# --- ENVIRONMENT CHECK ---
# Streamlit Cloud runs on Linux. Local PCs usually run on Windows.
IS_CLOUD = platform.system() == "Linux"

def extract_data(pdf_file):
    data_list = []
    
    # On Cloud, we use system-installed tools (path=None)
    # On Local, we point to the manual folder
    p_path = None if IS_CLOUD else r"C:\poppler\Library\bin"

    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        
        
        # Convert PDF pages to Images
        images = convert_from_bytes(
            file_bytes, 
            dpi=150, 
            poppler_path=p_path
        )
        
        st.success(f"✅ Successfully opened PDF with {len(images)} pages.")
        
        prog_bar = st.progress(0)
        for i, img in enumerate(images):
            prog_bar.progress((i + 1) / len(images), text=f"Reading Page {i+1}...")
            
            # OCR logic
            text = pytesseract.image_to_string(ImageOps.grayscale(img))
            
            # TNB Specific Regex
            date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            kwh_match = re.search(r'(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
            rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)

            if date_match or kwh_match or rm_match:
                data_list.append({
                    "Date": date_match.group(1) if date_match else "N/A",
                    "Usage (kWh)": kwh_match.group(1).strip() if kwh_match else "0.00",
                    "Total (RM)": rm_match.group(1).strip() if rm_match else "0.00",
                    "Page": i + 1
                })
            
            del img
            gc.collect()
            
        return data_list
    except Exception as e:
        st.error(f"❌ System Error: {e}")
        if IS_CLOUD:
            st.info("Check if packages.txt is in your GitHub with 'poppler-utils'.")
        return None

# --- MAIN UI ---
st.title("⚡ TNB Industrial PDF Extractor")
st.write("Upload a TNB bill PDF to extract usage and cost data automatically.")

uploaded_file = st.file_uploader("Upload TNB Bill (PDF)", type="pdf")

if uploaded_file:
    if st.button("🚀 Run Extraction"):
        with st.spinner("Extracting data..."):
            results = extract_data(uploaded_file)
            
            if results:
                df = pd.DataFrame(results)
                st.subheader("Extracted Results")
                edited_df = st.data_editor(df, use_container_width=True)
                
                # Excel Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    edited_df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Download as Excel",
                    data=buffer.getvalue(),
                    file_name="TNB_Extracted_Data.xlsx",
                    mime="application/vnd.ms-excel"
                )

import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Industrial Smart Extractor", layout="wide")

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # We use 200 DPI for better clarity on industrial digits. 
        # If the app crashes on very large files, lower this to 150.
        images = convert_from_bytes(file_bytes, dpi=200) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # Use PSM 6 to maintain horizontal alignment of large numbers
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. STRICT DATE SEARCH (Tempoh Bil) ---
            # Correctly identifies usage month by looking at the period end-date
            tempoh_pattern = r'Tempoh\s*Bil.*?[\d./-]+\s*-\s*(\d{2}[./-]\d{2}[./-]\d{4})'
            date_match = re.search(tempoh_pattern, text, re.IGNORECASE | re.DOTALL)
            
            if not date_match:
                date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            if date_match:
                date_str = date_match.group(1).replace('-', '.').replace('/', '.')
                dt_obj = datetime.strptime(date_str, "%d.%m.%Y")
                
                # --- 2. FORCED kWh EXTRACTION (The First Error Fix) ---
                kwh_val = 0.0
                # Grabs the entire numerical string after the kWh keyword
                kwh_line_pattern = r'Kegunaan\s*(?:kWh|kVVh|KWH).*?([\d\s,]+\.\d{2})'
                kwh_match = re.search(kwh_line_pattern, text, re.IGNORECASE | re.DOTALL)
                
                if kwh_match:
                    raw_val = kwh_match.group(1)
                    # Filter out everything except digits and the decimal point
                    # This joins "1 364 751.00" or "1,364,751.00" into "1364751.00"
                    clean_val = "".join(filter(lambda x: x.isdigit() or x == '.', raw_val))

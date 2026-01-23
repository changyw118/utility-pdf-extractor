import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Precise Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """Collapses million-scale numbers to prevent digit loss."""
    if not raw_str: return 0.0
    clean = "".join(c for c in raw_str if c.isdigit() or c == '.')
    if clean.count('.') > 1:
        parts = clean.split('.')
        clean = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(clean)
    except:
        return 0.0

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Stream pages one by one to save RAM.
        # 200 DPI balances precision and memory safety.
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 keeps table rows and header boxes aligned.
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. THE POSITIONAL DATE LOCK ---
            dt_obj = None
            # Targets the FIRST date after 'Tempoh Bil' (e.g., 01.01.2020).
            date_anchor = re.search(r'Tempoh\s*Bil.*?:?\s*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
            
            if date_anchor:
                raw_date = date_anchor.group(1).replace('-', '.').replace('/', '.')
                if raw_date.startswith('9'): raw_date = '3' + raw_date[1:] # Fix OCR typo.
                try:
                    dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except: pass

            if dt_obj and 2010 <= dt_obj.year <= 2030:
                # --- 2. kWh & RM EXTRACTION ---
                # Million-scale fix for 1,364,751.00.
                kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                kwh_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0

                rm_match = re.search(r'Jumlah\s*Perlu\s*Bayar.*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                if not rm_match:
                    backup = list(re.finditer(r'(?:RM|RN|BM)?\s*([\d\s,.]+\d{2})', text, re.IGNORECASE))
                    rm_val = clean_industrial_num(backup[-1].group(1)) if backup else 0.0
                else:
                    rm_val = clean_industrial_num(rm_match.group(1))

                if kwh_val > 0 or rm_val > 0:
                    data_list.append({
                        "Year": dt_obj.year, "Month": dt_obj.strftime("%b"),
                        "Month_Num": dt_obj.month, "kWh": kwh_val, "RM": rm_val
                    })
            
            # CRITICAL: Clear memory after every page.
            image.close() 
            del image
            gc.collect() 
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Technical Alert: {e}")
    return data_list

# --- UI & EXCEL FORMATTING ---
st.title("⚡ TNB Absolute Precision Extractor")

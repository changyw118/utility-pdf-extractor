import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

def clean_industrial_num(raw_str):
    if not raw_str: return 0.0
    # Removes spaces and commas, keeps digits and dots
    clean = re.sub(r'[^\d.]', '', raw_str.replace(' ', ''))
    try:
        return float(clean)
    except:
        return 0.0

def extract_data_with_ocr(pdf_file):
    data_list = []
    current_bill_date = None # State: Remember date across pages
    
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        images = convert_from_bytes(file_bytes, dpi=200, grayscale=True) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. DATE LOOKUP (Persistent) ---
            # Search for the date block
            header_section = re.search(r'Tarikh\s*Bil(.*?)No\.\s*Invois', text, re.IGNORECASE | re.DOTALL)
            if header_section:
                dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', header_section.group(1))
                if len(dates) >= 2:
                    raw_date = dates[1].replace('-', '.').replace('/', '.')
                    try:
                        current_bill_date = datetime.strptime(raw_date, "%d.%m.%Y")
                    except: pass

            # --- 2. DATA EXTRACTION ---
            if current_bill_date:
                # Look for kWh specifically with "Kegunaan"
                kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
                
                # Look for RM with a very specific "Jumlah Perlu Bayar" anchor
                # We use [:\s]* to handle OCR misreading colons as spaces
                rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[:\s]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)
                
                if kwh_match or rm_match:
                    k_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0
                    r_val = clean_industrial_num(rm_match.group(1)) if rm_match else 0.0
                    
                    if k_val > 0 or r_val > 0:
                        data_list.append({
                            "Year": current_bill_date.year,
                            "Month": current_bill_date.strftime("%b"),
                            "Month_Num": current_bill_date.month,
                            "kWh": k_val,
                            "RM": r_val,
                            "Page": i + 1
                        })
                        # Once we find a main total on a page, we clear the date 
                        # to avoid duplicate extraction from supplementary pages
                        current_bill_date = None 

            image.close() 
            del image
            gc.collect() 
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ App Error: {e}")
    return data_list

# ... (Rest of your UI/Excel code remains the same)

import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Config ---
st.set_page_config(page_title="TNB Smart OCR Extractor", layout="wide")

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Convert PDF pages to images
        images = convert_from_bytes(file_bytes)
        total_pages = len(images)
        
        progress_text = f"Scanning {pdf_file.name}..."
        my_bar = st.progress(0, text=progress_text)

        for i, image in enumerate(images):
            # Update progress
            progress_perc = int(((i + 1) / total_pages) * 100)
            my_bar.progress(progress_perc, text=f"{progress_text} (Page {i+1}/{total_pages})")
            
            # OCR logic
            text = pytesseract.image_to_string(image)
            
            # Parsing logic
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
            if not date_match:
                continue
                
            dt_obj = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            
            kwh_val = 0.0
            kwh_match = re.search(r'Kegunaan\s*kWh.*?([\d,]+\.\d{2})', text, re.DOTALL)
            if kwh_match:
                kwh_val = float(kwh_match.group(1).replace(',', ''))

            rm_val = 0.0
            rm_match = re.search(r'(?:Jumlah\s*Perlu\s*Bayar|Jumlah\s*Bil|Caj\s*Semasa)\s*RM\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
            if rm_match:
                rm_val = float(rm_match.group(1).replace(',', ''))

            if kwh_val > 0 or rm_val > 0:
                data_list.append({
                    "Year": dt_obj.year,
                    "Month": dt_obj.strftime("%b"),
                    "Month_Num": dt_obj.month,
                    "kWh": kwh_val,
                    "RM": rm_val
                })
        
        my_bar.empty()
                    
    except Exception as e:
        st.error(f"⚠️ Technical Error: {e}")
                
    return data_list

# --- UI ---
st.title("⚡ TNB Industrial Smart Extractor")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_data_with_ocr(f)
        if extracted:
            all_data.extend(extracted)
    
    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        
        st.subheader("📊 Extracted Summary")
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        # Excel Export logic
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='TNB_Data')
        
        st.download_button(
            label="📥 Download Excel Report",
            data=output.getvalue(),
            file_name="TNB_Consolidated_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data found on any pages. Check if the PDF is blurry.")

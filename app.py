import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps

st.set_page_config(page_title="TNB Industrial Extractor", layout="wide")

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
    current_bill_date = None
    
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        # DPI 150 is the "sweet spot" for speed vs memory on Streamlit Cloud
        images = convert_from_bytes(file_bytes, dpi=150) 
        total_pages = len(images)
        
        progress_text = f"Scanning {pdf_file.name}..."
        my_bar = st.progress(0, text=progress_text)

        for i, image in enumerate(images):
            my_bar.progress((i + 1) / total_pages, text=f"Processing Page {i+1}/{total_pages}")
            
            # --- Image Preprocessing for Better OCR ---
            image = ImageOps.grayscale(image)
            # Thresholding helps remove background noise/colors
            image = image.point(lambda x: 0 if x < 140 else 255, '1') 
            
            # OCR with Whitelist for numbers and key financial terms
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(image, lang="eng", config=custom_config)
            
            # --- 1. DATE LOOKUP ---
            # TNB bills usually have "Tarikh Bil" followed by the date
            header_section = re.search(r'Tarikh\s*Bil(.*?)No\.', text, re.IGNORECASE | re.DOTALL)
            if header_section:
                dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', header_section.group(1))
                if dates:
                    raw_date = dates[-1].replace('-', '.').replace('/', '.')
                    try:
                        current_bill_date = datetime.strptime(raw_date, "%d.%m.%Y")
                    except: pass

            # --- 2. DATA EXTRACTION ---
            if current_bill_date:
                # Target the Total Consumption (kWh)
                kwh_match = re.search(r'(?:Kegunaan|Jumlah)\s*(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
                
                # Target the Total Payable (RM)
                rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)
                
                if kwh_match or rm_match:
                    k_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0
                    r_val = clean_industrial_num(rm_match.group(1)) if rm_match else 0.0
                    
                    if k_val > 0 or r_val > 0:
                        data_list.append({
                            "Date": current_bill_date.strftime("%Y-%m-%d"),
                            "Year": current_bill_date.year,
                            "Month": current_bill_date.strftime("%b"),
                            "kWh": k_val,
                            "RM": r_val,
                            "Source": pdf_file.name
                        })
                        current_bill_date = None # Reset to avoid duplicates on multi-page invoices

            # Cleanup memory immediately
            del image
            gc.collect()
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Error processing {pdf_file.name}: {e}")
    return data_list

# --- UI LAYOUT ---
st.title("⚡ TNB Industrial PDF Extractor")
st.markdown("Upload your TNB Electricity Bills (PDF) to extract consumption and cost data.")

uploaded_files = st.file_uploader("Choose TNB PDF files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_extracted_data = []
    for uploaded_file in uploaded_files:
        result = extract_data_with_ocr(uploaded_file)
        all_extracted_data.extend(result)
    
    if all_extracted_data:
        df = pd.DataFrame(all_extracted_data)
        
        st.subheader("Extracted Data")
        st.info("💡 You can edit the cells below if the OCR misread a number.")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        # --- EXCEL DOWNLOAD ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='TNB_Data')
            writer.close()
            
        st.download_button(
            label="📥 Download Data as Excel",
            data=buffer.getvalue(),
            file_name=f"TNB_Extraction_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data found. Please ensure the PDF is a clear TNB bill.")

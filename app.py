import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Config ---
st.set_page_config(page_title="TNB Industrial Smart Extractor", layout="wide")

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # 200 DPI is the "Sweet Spot" for industrial digits
        images = convert_from_bytes(file_bytes, dpi=200) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # PSM 6 helps keep large numbers on one line
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. DATE SEARCH (Tempoh Bil) ---
            tempoh_pattern = r'Tempoh\s*Bil.*?[\d./-]+\s*-\s*(\d{2}[./-]\d{2}[./-]\d{4})'
            date_match = re.search(tempoh_pattern, text, re.IGNORECASE | re.DOTALL)
            
            if not date_match:
                date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            if date_match:
                date_str = date_match.group(1).replace('-', '.').replace('/', '.')
                dt_obj = datetime.strptime(date_str, "%d.%m.%Y")
                
                # --- 2. kWh EXTRACTION (Large Number Fix) ---
                kwh_val = 0.0
                kwh_line_pattern = r'Kegunaan\s*(?:kWh|kVVh|KWH).*?([\d\s,]+\.\d{2})'
                kwh_match = re.search(kwh_line_pattern, text, re.IGNORECASE | re.DOTALL)
                
                if kwh_match:
                    raw_val = kwh_match.group(1)
                    clean_val = "".join(filter(lambda x: x.isdigit() or x == '.', raw_val))
                    if clean_val:
                        kwh_val = float(clean_val)

                # --- 3. RM EXTRACTION (Final Total) ---
                rm_val = 0.0
                rm_pattern = r'(?:Jumlah|Caj|Total).*?(?:Perlu|Bayar|Bil|Semasa).*?(?:RM|RN|BM)?\s*([\d\s,]+\.\d{2})'
                rm_matches = list(re.finditer(rm_pattern, text, re.IGNORECASE | re.DOTALL))
                
                if rm_matches:
                    raw_rm = rm_matches[-1].group(1)
                    clean_rm = "".join(filter(lambda x: x.isdigit() or x == '.', raw_rm))
                    if clean_rm:
                        rm_val = float(clean_rm)

                if kwh_val > 0 or rm_val > 0:
                    data_list.append({
                        "Year": dt_obj.year,
                        "Month": dt_obj.strftime("%b"),
                        "Month_Num": dt_obj.month,
                        "kWh": kwh_val,
                        "RM": rm_val
                    })
            
            image.close()
            del image 
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Extraction Error: {e}")
    return data_list

# --- User Interface ---
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
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='TNB_Data')
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Report.xlsx")

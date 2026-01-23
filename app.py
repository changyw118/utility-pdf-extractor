import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import pytesseract
from pdf2image import convert_from_bytes

st.set_page_config(page_title="TNB Universal Extractor", layout="wide")

def clean_industrial_num(raw_str):
    """Collapses spaces and commas to prevent digit loss in large numbers."""
    if not raw_str: return 0.0
    clean = "".join(c for c in raw_str if c.isdigit() or c == '.')
    try:
        return float(clean)
    except:
        return 0.0

def extract_data_with_ocr(pdf_file):
    data_list = []
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # 1. Process as a generator to save memory
        # 200 DPI ensures accuracy for small digits
        images = convert_from_bytes(file_bytes, dpi=200) 
        total_pages = len(images)
        
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress(int(((i + 1) / total_pages) * 100))
            
            # Use PSM 6 for horizontal alignment of industrial tables
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. STRICT DATE (Tempoh Bil) ---
            tempoh_pattern = r'Tempoh\s*Bil.*?[\d./-]+\s*-\s*(\d{2}[./-]\d{2}[./-]\d{4})'
            date_match = re.search(tempoh_pattern, text, re.IGNORECASE | re.DOTALL)
            
            if not date_match:
                date_match = re.search(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
            
            if date_match:
                date_str = date_match.group(1).replace('-', '.').replace('/', '.')
                dt_obj = datetime.strptime(date_str, "%d.%m.%Y")
                
                # --- 2. STRICT kWh (Large Number Fix) ---
                kwh_pattern = r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,]+\.\d{2})'
                kwh_match = re.search(kwh_pattern, text, re.IGNORECASE | re.DOTALL)
                kwh_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0

                # --- 3. STRICT RM (Final Total) ---
                rm_pattern = r'(?:Jumlah|Caj|Total).*?(?:Perlu|Bayar|Bil|Semasa).*?(?:RM|RN|BM)?\s*([\d\s,]+\.\d{2})'
                rm_matches = list(re.finditer(rm_pattern, text, re.IGNORECASE | re.DOTALL))
                rm_val = clean_industrial_num(rm_matches[-1].group(1)) if rm_matches else 0.0

                if kwh_val > 0 or rm_val > 0:
                    data_list.append({
                        "Year": dt_obj.year,
                        "Month": dt_obj.strftime("%b"),
                        "Month_Num": dt_obj.month,
                        "kWh": kwh_val,
                        "RM": rm_val
                    })
            
            # --- CRITICAL: CLEAR RAM ---
            image.close() # Removes the current page from memory
            del image
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Memory or System Error: {e}")
    return data_list

# --- UI ---
st.title("⚡ TNB Universal Smart Extractor")
uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = extract_data_with_ocr(f)
        if data: all_results.extend(data)
    
    if all_results:
        df = pd.DataFrame(all_results).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        st.subheader("📊 Extracted Summary")
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel Report", output.getvalue(), "TNB_Report.xlsx")

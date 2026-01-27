import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("🔧 Environment Settings")
st.sidebar.info("If running locally on Windows, provide the paths below.")

# Poppler Path (Needed for pdf2image)
poppler_bin_path = st.sidebar.text_input(
    "Poppler Bin Path", 
    placeholder=r"C:\poppler\Library\bin"
)

# Tesseract Path (Needed for pytesseract)
tesseract_exe_path = st.sidebar.text_input(
    "Tesseract EXE Path", 
    placeholder=r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Apply Tesseract path if provided
if tesseract_exe_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_exe_path

# --- HELPER FUNCTIONS ---
def clean_industrial_num(raw_str):
    if not raw_str: return 0.0
    # Removes spaces and commas, keeps digits and dots
    clean = re.sub(r'[^\d.]', '', raw_str.replace(' ', ''))
    try:
        return float(clean)
    except:
        return 0.0

def extract_data_with_ocr(pdf_file, p_path):
    data_list = []
    current_bill_date = None 
    
    try:
        pdf_file.seek(0)
        file_bytes = pdf_file.read()
        
        # Convert PDF to Images
        # We pass the poppler_path here from the sidebar input
        pop_param = p_path if p_path else None
        
        images = convert_from_bytes(
            file_bytes, 
            dpi=150, 
            grayscale=True, 
            poppler_path=pop_param
        )
        
        total_pages = len(images)
        my_bar = st.progress(0, text=f"Scanning {pdf_file.name}...")

        for i, image in enumerate(images):
            my_bar.progress((i + 1) / total_pages)
            
            # Simple Pre-processing
            image = ImageOps.autocontrast(image)
            text = pytesseract.image_to_string(image, lang="eng", config='--psm 6')
            
            # --- 1. DATE LOOKUP (Search for Tarikh Bil) ---
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
                # Look for kWh and Amount RM
                kwh_match = re.search(r'(?:Kegunaan|Jumlah)\s*(?:kWh|KWH|kVVh)[\s:]*([\d\s,.]+\d{2})', text, re.IGNORECASE)
                rm_match = re.search(r'Jumlah\s+Perlu\s+Bayar[\s:]*RM\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)
                
                if kwh_match or rm_match:
                    k_val = clean_industrial_num(kwh_match.group(1)) if kwh_match else 0.0
                    r_val = clean_industrial_num(rm_match.group(1)) if rm_match else 0.0
                    
                    if k_val > 0 or r_val > 0:
                        data_list.append({
                            "Billing Date": current_bill_date.strftime("%Y-%m-%d"),
                            "Year": current_bill_date.year,
                            "Month": current_bill_date.strftime("%b"),
                            "kWh": k_val,
                            "RM": r_val,
                            "File": pdf_file.name
                        })
                        current_bill_date = None # Clear date to avoid multi-page duplicates

            image.close()
            del image
            gc.collect()
            
        my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Error processing {pdf_file.name}: {e}")
        st.info("Tip: Double check your Poppler path in the sidebar.")
    return data_list

# --- MAIN UI ---
st.title("⚡ TNB Industrial Bill Extractor")
st.write("Upload scanned TNB PDFs to extract Billing Date, Usage (kWh), and Total Amount (RM).")

files = st.file_uploader("Upload TNB PDF Bills", type="pdf", accept_multiple_files=True)

if files:
    all_data = []
    for f in files:
        data = extract_data_with_ocr(f, poppler_bin_path)
        all_data.extend(data)
    
    if all_data:
        df = pd.DataFrame(all_data)
        
        st.subheader("Results")
        # Editable table for manual corrections
        edited_df = st.data_editor(df, use_container_width=True)
        
        # Excel Download Logic
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='TNB_Data')
        
        st.download_button(
            label="📊 Export to Excel",
            data=output.getvalue(),
            file_name=f"TNB_Export_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

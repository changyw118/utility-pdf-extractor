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
    pdf_file.seek(0)
    file_bytes = pdf_file.read()
    
    try:
        # Step A: Convert PDF pages to images
        # We don't limit pages anymore so it reads all of them
        images = convert_from_bytes(file_bytes)
        total_pages = len(images)
        
        # Create a progress bar in the UI
        progress_text = f"Scanning {pdf_file.name}..."
        my_bar = st.progress(0, text=progress_text)

        # Step B: Loop through every single page
        for i, image in enumerate(images):
            # Update progress bar
            progress_perc = int(((i + 1) / total_pages) * 100)
            my_bar.progress(progress_perc, text=f"{progress_text} (Page {i+1}/{total_pages})")
            
            # Perform OCR on the current page
            text = pytesseract.image_to_string(image)
            
            # Step C: Parse the data using Regex
            # 1. Look for Date (01.01.2019)
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
            if not date_match:
                continue # Skip page if no date found
                
            dt_obj = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            
            # 2. Look for kWh Usage
            kwh_val = 0.0
            kwh_match = re.search(r'Kegunaan\s*kWh.*?([\d,]+\.\d{2})', text, re.DOTALL)
            if kwh_match:
                kwh_val = float(kwh_match.group(1).replace(',', ''))

            # 3. Look for Total RM Cost
            rm_val = 0.0
            rm_match = re.search(r'(?:Jumlah\s*Perlu\s*Bayar|Jumlah\s*Bil|Caj\s*Semasa)\s*RM\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
            if rm_match:
                rm_val = float(rm_match.group(1).replace(',', ''))

            # Save data if we found something useful
            if kwh_val > 0 or rm_val > 0:
                data_list.append({
                    "Year": dt_obj.year,
                    "Month": dt_obj.strftime("%b"),
                    "Month_Num": dt_obj.month,
                    "kWh": kwh_val,
                    "RM": rm_val
                })
        
        my_bar.empty() # Remove progress bar when done
                    
    except Exception as e:
        st.error(f"⚠️ Error processing {pdf_file.name}: {e}")
                
    return data_list

# --- UI Layout ---
st.title("⚡ TNB Industrial Smart Extractor")
st.markdown("Upload your TNB PDFs. The app will now scan **every page** automatically.")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_data_with_ocr(f)
        if extracted:
            all_data.extend(extracted)
    
    if all_data:
        # Create DataFrame and remove duplicates (if same month appears twice)
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month']).sort_values(['Year', 'Month_Num'])
        
        st.subheader("📊 Extracted Summary")
        st.table(df[['Year', 'Month', 'kWh', 'RM']].style.format({'kWh': "{:,.2f}", 'RM': "{:,.2f}"}))
        
        # Create Excel file in memory
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
        st.warning("No data found. Please ensure the PDF contains the keywords 'Kegunaan kWh' or 'RM'.")

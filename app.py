import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Industrial Data Extractor", layout="wide")

def extract_tnb_data(pdf_file):
    data_list = []
    pdf_file.seek(0)
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Analyze all pages to ensure we catch the right data
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                
                lines = text.split('\n')
                current_kwh = 0.0
                current_rm = 0.0
                current_date = None

                for i, line in enumerate(lines):
                    # 1. EXTRACT DATE: Look for the date pattern DD.MM.YYYY 
                    if not current_date:
                        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', line)
                        if date_match:
                            current_date = datetime.strptime(date_match.group(1), "%d.%m.%Y")

                    # 2. EXTRACT kWh: Find "Kegunaan kWh" and look at the end of that line [cite: 16, 109]
                    if "Kegunaan kWh" in line:
                        nums = re.findall(r'[\d,]+\.\d{2}', line)
                        if nums:
                            current_kwh = float(nums[-1].replace(',', ''))

                    # 3. EXTRACT RM: Find "Jumlah Perlu Bayar" [cite: 6, 103, 201]
                    if "Jumlah Perlu Bayar" in line or "Jumlah Bil" in line:
                        rm_nums = re.findall(r'[\d,]+\.\d{2}', line)
                        if rm_nums:
                            current_rm = float(rm_nums[-1].replace(',', ''))

                if current_date and (current_kwh > 0 or current_rm > 0):
                    data_list.append({
                        "Year": current_date.year,
                        "Month": current_date.strftime("%b"),
                        "Month_Num": current_date.month,
                        "kWh": current_kwh,
                        "RM": current_rm
                    })
                    # Stop after finding valid data for this bill (to avoid duplicate page data)
                    break
                    
    except Exception as e:
        st.error(f"Error processing file: {e}")
                
    return data_list

# --- STREAMLIT UI ---
st.title("⚡ TNB Industrial Data Extractor")
st.markdown("This version uses **Line-by-Line scanning** for Panasonic Industrial Bills.")

uploaded_files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    for f in uploaded_files:
        extracted = extract_tnb_data(f)
        if extracted:
            all_data.extend(extracted)
    
    if all_data:
        # Create DataFrame and remove duplicates
        df = pd.DataFrame(all_data).drop_duplicates(subset=['Year', 'Month'])
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # Display Tables
        st.subheader("Summary Table")
        final_df = df.sort_values(by=['Year', 'Month_Num'])
        st.dataframe(final_df[['Year', 'Month', 'kWh', 'RM']], use_container_width=True)
        
        # Excel Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='TNB_Data', index=False)
        
        st.download_button("📥 Download Excel File", output.getvalue(), "TNB_Consolidated_Data.xlsx")
    else:
        st.error("Still no data. Please verify your PDF is a 'Digital PDF' (you can highlight the text with your mouse).")

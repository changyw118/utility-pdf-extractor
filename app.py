import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="PDF Utility Extractor", layout="wide")

st.title("📊 Utility Data Extractor")
st.markdown("Upload your text-based PDF bills to extract Usage (kWh) and Charges (RM).")

def clean_numeric(text):
    """Removes commas from numbers to make them float-friendly."""
    return text.replace(',', '')

def extract_utility_data(pdf_file):
    extracted_rows = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            # --- REGEX PATTERNS ---
            # 1. Date: Looks for DD.MM.YYYY
            date_pattern = r'(\d{2}\.\d{2}\.\d{4})'
            # 2. kWh: Looks for a number before 'kWh' (handles commas and decimals)
            kwh_pattern = r'([\d,]+\.\d{2})\s+kWh'
            # 3. RM: Looks for amount after 'Caj Semasa'
            rm_pattern = r'Caj Semasa.*?RM\s*([\d,]+\.\d{2})'

            # Finding matches
            dates = re.findall(date_pattern, text)
            kwh_matches = re.findall(kwh_pattern, text)
            rm_matches = re.findall(rm_pattern, text)

            # Process the first valid date found on the page
            if dates:
                try:
                    raw_date = dates[0]
                    # Convert 01.01.2019 -> Jan 2019
                    date_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                    formatted_date = date_obj.strftime("%b %Y")
                except ValueError:
                    formatted_date = "Invalid Date"
            else:
                formatted_date = None

            # If we found at least a date and a kWh value, save it
            if formatted_date and kwh_matches:
                extracted_rows.append({
                    "Month/Year": formatted_date,
                    "Usage (kWh)": float(clean_numeric(kwh_matches[-1])), # Taking last column as requested
                    "Amount (RM)": float(clean_numeric(rm_matches[0])) if rm_matches else 0.0,
                    "Raw Date": dates[0]
                })
                
    return extracted_rows

# --- STREAMLIT UI ---
uploaded_file = st.file_uploader("Choose your PDF file", type="pdf")

if uploaded_file is not None:
    with st.spinner('Extracting data...'):
        data = extract_utility_data(uploaded_file)
        
        if data:
            df = pd.DataFrame(data)
            
            # Layout: Stats & Table
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.metric("Total Usage", f"{df['Usage (kWh)'].sum():,.2f} kWh")
                st.metric("Total Charges", f"RM {df['Amount (RM)'].sum():,.2f}")
            
            with col2:
                st.subheader("Extracted Data")
                st.dataframe(df, use_container_width=True)
            
            # Download Options
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv,
                file_name="extracted_billing_data.csv",
                mime="text/csv",
            )
        else:
            st.error("No data found. Please ensure the PDF is text-based and contains the expected keywords.")

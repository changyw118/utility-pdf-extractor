import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Data Extractor Pro", layout="wide")

def clean_val(text):
    """Removes RM, kWh, and commas, then converts to float."""
    if not text: return 0.0
    clean = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        return float(clean)
    except:
        return 0.0

def extract_tnb_data(pdf_file):
    extracted_data = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            # 1. Get Date (Tempoh Bill)
            # Looks for the pattern DD.MM.YYYY
            dates = re.findall(r'(\d{2}\.\d{2}\.\d{4})', text)
            if not dates: continue
            
            # We take the first date as the start of 'Tempoh Bill'
            raw_date = dates[0]
            dt = datetime.strptime(raw_date, "%d.%m.%Y")
            
            # 2. Get kWh and RM using a word-search method (more reliable)
            words = page.extract_words()
            
            kwh_value = 0.0
            rm_value = 0.0
            
            for i, w in enumerate(words):
                # Search for kWh: It is usually the number before the word 'kWh' 
                # or in the same row as 'Kegunaan'
                if "kWh" in w['text']:
                    # Check previous word
                    val = words[i-1]['text']
                    if "." in val:
                        kwh_value = clean_val(val)
                
                # Search for Caj Semasa RM
                if "Semasa" in w['text']:
                    # Look ahead a few words for the RM value
                    for j in range(i, min(i+10, len(words))):
                        if "RM" in words[j]['text'] or re.search(r'[\d,]+\.\d{2}', words[j]['text']):
                            rm_value = clean_val(words[j]['text'])
                            # If we found a value > 0, stop looking for RM
                            if rm_value > 0: break

            if kwh_value > 0 or rm_value > 0:
                extracted_data.append({
                    "Year": dt.year,
                    "Month": dt.strftime("%b"),
                    "Month_Num": dt.month,
                    "kWh": kwh_value,
                    "RM": rm_value
                })
                
    return extracted_data

# --- UI ---
st.title("⚡ TNB Automatic Bill Extractor")
st.markdown("Drop your PDF bills here to generate the comparison tables.")

files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

if files:
    results = []
    for f in files:
        data = extract_tnb_data(f)
        if data:
            results.extend(data)
        else:
            st.error(f"Could not extract data from {f.name}. The PDF might be a scan/image.")

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['Year', 'Month'])
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # --- KWH TABLE ---
        st.subheader("Summary Comparison Electricity Usage (kWh)")
        kwh_piv = df.pivot(index='Month', columns='Year', values='kWh').reindex(month_order)
        st.dataframe(kwh_piv.style.format("{:,.2f} kWh", na_rep="-"), use_container_width=True)
        
        # --- RM TABLE ---
        st.subheader("Summary Comparison Electricity Cost (RM)")
        rm_piv = df.pivot(index='Month', columns='Year', values='RM').reindex(month_order)
        st.dataframe(rm_piv.style.format("RM {:,.2f}", na_rep="-"), use_container_width=True)
        
        # --- DOWNLOAD ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            kwh_piv.to_excel(writer, sheet_name='kWh_Usage')
            rm_piv.to_excel(writer, sheet_name='RM_Cost')
        
        st.download_button("📥 Download Excel Summary", output.getvalue(), "TNB_Report.xlsx")

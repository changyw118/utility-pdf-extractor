import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc 
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes

# --- Page Configuration ---
st.set_page_config(page_title="TNB Precise Industrial Extractor Pro", layout="wide", page_icon="⚡")

# --- Design Tokens (Aesthetics) ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    h1 { color: #1E3A8A; font-family: 'Inter', sans-serif; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

def clean_industrial_num(raw_str):
    if not raw_str: return None
    match = re.search(r'[\d,.]*\d+\.\d{2}', raw_str)
    if not match: match = re.search(r'[\d,.]+', raw_str)
    if match:
        clean = "".join(c for c in match.group(0) if c.isdigit() or c == '.')
        if clean.count('.') > 1:
            parts = clean.split('.')
            clean = "".join(parts[:-1]) + "." + parts[-1]
        try:
            val = float(clean)
            return val if val > 0 else None
        except: return None
    return None

def extract_data_from_text(text):
    data = None
    dt_obj = None
    tempoh_match = re.search(r'Tempoh\s*Bil\s*:\s*.*?\s*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
    if tempoh_match:
        raw_date = tempoh_match.group(1).replace('-', '.').replace('/', '.')
        try: dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
        except: pass
    
    if not dt_obj:
        header_section = re.search(r'Tarikh\s*Bil(.*?)No\.\s*Invois', text, re.IGNORECASE | re.DOTALL)
        if header_section:
            dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', header_section.group(1))
            if len(dates) >= 2:
                raw_date = dates[1].replace('-', '.').replace('/', '.')
                try: dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except: pass

    if dt_obj and 2010 <= dt_obj.year <= 2030:
        kwh_val, rm_val = None, None
        new_kwh_match = re.search(r'Jumlah\s*Penggunaan\s*Anda\s*\(([\d\s,.]+)\s*kWh\)', text, re.IGNORECASE)
        kwh_val = clean_industrial_num(new_kwh_match.group(1)) if new_kwh_match else None
        
        new_rm_match = re.search(r'Caj\s*Semasa\s*(?:RM)?\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)
        if new_rm_match: rm_val = clean_industrial_num(new_rm_match.group(1))
        
        if kwh_val or rm_val:
            data = {"Year": int(dt_obj.year), "Month": dt_obj.strftime("%b"), "Month_Num": int(dt_obj.month), "kWh": kwh_val, "RM": rm_val, "Status": "Found"}
    return data

def process_pdf(pdf_file):
    data_map = {}
    with pdfplumber.open(pdf_file) as pdf:
        total_pages = len(pdf.pages)
        my_bar = st.progress(0, text=f"Processing {pdf_file.name}...")
        for i, page in enumerate(pdf.pages):
            my_bar.progress((i + 1) / total_pages)
            text = page.extract_text()
            page_data = extract_data_from_text(text) if text else None
            if not page_data:
                pdf_file.seek(0)
                images = convert_from_bytes(pdf_file.read(), first_page=i+1, last_page=i+1, dpi=200, grayscale=True)
                if images:
                    page_data = extract_data_from_text(pytesseract.image_to_string(images[0], lang="eng", config='--psm 6'))
                    images[0].close()
            if page_data:
                key = (page_data['Year'], page_data['Month_Num'])
                if key not in data_map: data_map[key] = page_data
        my_bar.empty()
    return list(data_map.values())

# --- UI Layout ---
st.title("⚡ TNB Industrial Smart Extractor Pro")
uploaded_files = st.file_uploader("📤 Upload TNB Industrial Bills (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for f in uploaded_files:
        data = process_pdf(f)
        if data: all_results.extend(data)
    
    if all_results:
        df = pd.DataFrame(all_results).sort_values(['Year', 'Month_Num'])
        df['Production Data'] = None
        
        # --- Create Pivot Comparison Table (Like your image) ---
        # We pivot the RM values, using Month names as index and Years as columns
        comparison_table = df.pivot_table(index='Month_Num', columns='Year', values='RM', aggfunc='sum')
        # Map Month_Num back to names
        month_names = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'June', 7:'July', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}
        comparison_table.index = comparison_table.index.map(month_names)
        comparison_table = comparison_table.reindex(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'June', 'July', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
        
        # Add Totals and Averages
        comparison_table.loc['Total Cost (RM)'] = comparison_table.sum()
        comparison_table.loc['Average Cost (RM)'] = comparison_table.iloc[:-1].mean()

        st.subheader("📋 Year-over-Year RM Comparison")
        st.dataframe(comparison_table.style.format("RM {:,.2f}", na_rep="-"))

        st.subheader("📊 Detailed Data Log")
        st.table(df[['Year', 'Month', 'kWh', 'RM', 'Production Data', 'Status']].fillna('-'))

        # --- Excel Export with Two Sheets ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Sheet 1: Pivot Summary
            comparison_table.to_excel(writer, sheet_name='Summary_Comparison')
            # Sheet 2: Raw Data
            df[['Year', 'Month', 'kWh', 'RM', 'Production Data', 'Status']].to_excel(writer, index=False, sheet_name='Monthly_Log')
            
            # Formatting the Summary Sheet
            workbook = writer.book
            ws_sum = writer.sheets['Summary_Comparison']
            money_fmt = workbook.add_format({'num_format': '"RM" #,##0.00', 'border': 1})
            header_fmt = workbook.add_format({'bg_color': '#1E3A8A', 'font_color': 'white', 'bold': True, 'border': 1})
            
            # Applying styles to summary columns
            ws_sum.set_column(1, len(comparison_table.columns), 18, money_fmt)
            
        st.download_button(
            label="📥 Download Summary & Data Export",
            data=output.getvalue(),
            file_name=f"TNB_Comparison_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Upload PDF bills to generate the Year-over-Year comparison table.")

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
    if not match:
        match = re.search(r'[\d,.]+', raw_str)
    if match:
        clean = "".join(c for c in match.group(0) if c.isdigit() or c == '.')
        if clean.count('.') > 1:
            parts = clean.split('.')
            clean = "".join(parts[:-1]) + "." + parts[-1]
        try:
            val = float(clean)
            return val if val > 0 else None
        except:
            return None
    return None

def extract_data_from_text(text):
    data = None
    dt_obj = None
    
    # Date extraction logic
    tempoh_match = re.search(r'Tempoh\s*Bil\s*:\s*.*?\s*(\d{2}[./-]\d{2}[./-]\d{4})', text, re.IGNORECASE)
    if tempoh_match:
        raw_date = tempoh_match.group(1).replace('-', '.').replace('/', '.')
        try:
            dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
        except: pass
    
    if not dt_obj:
        header_section = re.search(r'Tarikh\s*Bil(.*?)No\.\s*Invois', text, re.IGNORECASE | re.DOTALL)
        if header_section:
            dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', header_section.group(1))
            if len(dates) >= 2:
                raw_date = dates[1].replace('-', '.').replace('/', '.')
                try:
                    dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
                except: pass
                
    if not dt_obj:
        dates = re.findall(r'(\d{2}[./-]\d{2}[./-]\d{4})', text)
        if len(dates) >= 2:
            raw_date = dates[1].replace('-', '.').replace('/', '.')
            try:
                dt_obj = datetime.strptime(raw_date, "%d.%m.%Y")
            except: pass

    if dt_obj and 2010 <= dt_obj.year <= 2030:
        kwh_val = None
        rm_val = None

        new_kwh_match = re.search(r'Jumlah\s*Penggunaan\s*Anda\s*\(([\d\s,.]+)\s*kWh\)', text, re.IGNORECASE)
        if new_kwh_match:
            kwh_val = clean_industrial_num(new_kwh_match.group(1))
        else:
            old_kwh_match = re.search(r'Kegunaan\s*(?:kWh|KWH|kVVh).*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
            if old_kwh_match:
                kwh_val = clean_industrial_num(old_kwh_match.group(1))

        new_rm_match = re.search(r'Caj\s*Semasa\s*(?:RM)?\s*([\d\s,.]+\d{2})', text, re.IGNORECASE)
        if new_rm_match:
            rm_val = clean_industrial_num(new_rm_match.group(1))
        
        if rm_val is None:
            old_rm_match = re.search(r'Jumlah\s*Perlu\s*Bayar.*?([\d\s,.]+\d{2})', text, re.IGNORECASE | re.DOTALL)
            if old_rm_match:
                rm_val = clean_industrial_num(old_rm_match.group(1))

        if kwh_val or rm_val:
            data = {
                "Year": dt_obj.year,
                "Month_Num": dt_obj.month,
                "kWh": kwh_val,
                "RM": rm_val
            }
    return data

def process_pdf(pdf_file):
    data_map = {} 
    try:
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            progress_text = f"Processing {pdf_file.name}..."
            my_bar = st.progress(0, text=progress_text)
            
            for i, page in enumerate(pdf.pages):
                my_bar.progress((i + 1) / total_pages, text=f"{progress_text} (Page {i+1}/{total_pages})")
                text = page.extract_text()
                page_data = None
                
                if text and len(text.strip()) > 50:
                    page_data = extract_data_from_text(text)
                
                if not page_data:
                    pdf_file.seek(0)
                    images = convert_from_bytes(pdf_file.read(), first_page=i+1, last_page=i+1, dpi=200)
                    if images:
                        ocr_text = pytesseract.image_to_string(images[0])
                        page_data = extract_data_from_text(ocr_text)
                        del images
                
                if page_data:
                    key = (page_data['Year'], page_data['Month_Num'])
                    if key not in data_map:
                        data_map[key] = page_data
                    else:
                        if page_data['kWh']: data_map[key]['kWh'] = page_data['kWh']
                        if page_data['RM']: data_map[key]['RM'] = page_data['RM']
                
                if i % 10 == 0: gc.collect()
            my_bar.empty()
    except Exception as e:
        st.error(f"⚠️ Error processing {pdf_file.name}: {e}")
    return list(data_map.values())

# --- UI Layout ---
st.title("⚡ TNB Industrial Smart Extractor Pro")
st.markdown("Extract and organize bill data by Year and Month into formatted Excel tables.")

uploaded_files = st.file_uploader("📤 Upload TNB Industrial Bills (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    with st.spinner("Analyzing files..."):
        for f in uploaded_files:
            data = process_pdf(f)
            if data: all_results.extend(data)
    
    if all_results:
        # 1. Create Base DataFrame
        df_raw = pd.DataFrame(all_results)
        
        # 2. Ensure all months 1-12 are represented for each year found
        years = sorted(df_raw['Year'].unique())
        months = list(range(1, 13))
        
        # Create a template of Year/Month combinations
        template = pd.DataFrame([(y, m) for y in years for m in months], columns=['Year', 'Month_Num'])
        
        # Merge extracted data into the template
        df_merged = pd.merge(template, df_raw, on=['Year', 'Month_Num'], how='left')
        
        # Helper for Month Names
        month_names = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'June', 
                       7:'July', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}

        # --- EXCEL EXPORT LOGIC ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            
            # --- Table 1: kWh Consumption ---
            kwh_pivot = df_merged.pivot(index='Month_Num', columns='Year', values='kWh')
            kwh_pivot.index = kwh_pivot.index.map(month_names)
            # Add Total Row
            kwh_pivot.loc['Total kWh per year'] = kwh_pivot.sum()
            kwh_pivot.to_excel(writer, sheet_name='Consumption_kWh')

            # --- Table 2: RM Cost ---
            rm_pivot = df_merged.pivot(index='Month_Num', columns='Year', values='RM')
            rm_pivot.index = rm_pivot.index.map(month_names)
            # Add Total Row
            rm_pivot.loc['Total Cost (RM) per year'] = rm_pivot.sum()
            rm_pivot.to_excel(writer, sheet_name='Cost_RM')

            # --- Styling ---
            workbook = writer.book
            num_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
            
            for sheet_name in ['Consumption_kWh', 'Cost_RM']:
                worksheet = writer.sheets[sheet_name]
                # Format headers
                for col_num, value in enumerate(kwh_pivot.columns.values):
                    worksheet.write(0, col_num + 1, value, header_format)
                worksheet.write(0, 0, "Month/Year", header_format)
                
                # Format data and columns
                worksheet.set_column(1, len(years), 18, num_format)
                worksheet.set_column(0, 0, 25, header_format)

        st.success("Analysis Complete!")
        st.download_button(
            label="📥 Download Full Year-on-Year Report",
            data=output.getvalue(),
            file_name=f"TNB_Full_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Preview in Streamlit
        st.subheader("Preview (Current Year)")
        st.write(df_merged[df_merged['Year'] == max(years)].sort_values('Month_Num'))

else:
    st.info("Please upload PDF files to begin extraction.")

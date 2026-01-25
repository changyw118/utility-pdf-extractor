import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="TNB Precise Extractor", layout="wide")

def clean_num(s):
    if not s:
        return 0.0
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s)
    except:
        return 0.0

def extract_pdf(pdf_file):
    rows = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            rm_match = re.search(
                r"Jumlah\s+Perlu\s+Bayar\s*:\s*RM\s*([\d,]+\.\d{2})",
                text
            )
            kwh_match = re.search(
                r"\bJumlah\b\s+([\d,]+\.\d{2})",
                text
            )
            date_match = re.search(
                r"Tempoh\s+Bil\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
                text
            )

            if rm_match and kwh_match and date_match:
                dt = datetime.strptime(
                    date_match.group(1).replace("/", "."),
                    "%d.%m.%Y"
                )

                rows.append({
                    "Year": dt.year,
                    "Month": dt.strftime("%b"),
                    "Month_Num": dt.month,
                    "kWh": clean_num(kwh_match.group(1)),
                    "RM": clean_num(rm_match.group(1))
                })

    return rows

st.title("⚡ TNB Industrial Smart Extractor")

files = st.file_uploader("Upload TNB PDFs", type="pdf", accept_multiple_files=True)

if files:
    data = []
    for f in files:
        data.extend(extract_pdf(f))

    if data:
        df = (
            pd.DataFrame(data)
            .drop_duplicates(subset=["Year", "Month"])
            .sort_values(["Year", "Month_Num"])
        )

        st.table(
            df[["Year", "Month", "kWh", "RM"]]
            .style.format({"kWh": "{:,.2f}", "RM": "{:,.2f}"})
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df[["Year", "Month", "kWh", "RM"]].to_excel(writer, index=False)

        st.download_button(
            "Download Excel",
            output.getvalue(),
            "TNB_Report.xlsx"
        )

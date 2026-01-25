import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(
    page_title="TNB Single-Page Extractor",
    layout="wide"
)

# -------------------------------
# Utilities
# -------------------------------
def clean_number(s):
    if not s:
        return 0.0
    s = re.sub(r"[^\d.]", "", s)
    try:
        return float(s)
    except:
        return 0.0


def extract_from_page(text):
    # 1) Jumlah Perlu Bayar
    rm_match = re.search(
        r"Jumlah\s+Perlu\s+Bayar\s*:\s*RM\s*([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )
    rm = clean_number(rm_match.group(1)) if rm_match else 0.0

    # 2) Jumlah kWh (exact line)
    kwh_match = re.search(
        r"\bJumlah\b\s+([\d,]+\.\d{2})",
        text
    )
    kwh = clean_number(kwh_match.group(1)) if kwh_match else 0.0

    # 3) Tempoh Bil start date
    date_match = re.search(
        r"Tempoh\s+Bil\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
        text,
        re.IGNORECASE
    )
    dt = None
    if date_match:
        try:
            dt = datetime.strptime(
                date_match.group(1).replace("/", "."),
                "%d.%m.%Y"
            )
        except:
            pass

    return kwh, rm, dt


def extract_pdf(pdf_file):
    rows = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            kwh, rm, dt = extract_from_page(text)

            if dt and (kwh > 0 or rm > 0):
                rows.append({
                    "Year": dt.year,
                    "Month": dt.strftime("%b"),
                    "Month_Num": dt.month,
                    "kWh": kwh,
                    "RM": rm
                })

    return rows


# -------------------------------
# UI
# -------------------------------
st.title("⚡ TNB Precise Single-Page Extractor")

files = st.file_uploader(
    "Upload TNB PDF",
    type="pdf",
    accept_multiple_files=True
)

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

        st.subheader("Extracted Data")
        st.table(
            df[["Year", "Month", "kWh", "RM"]]
            .style.format({"kWh": "{:,.2f}", "RM": "{:,.2f}"})
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df[["Year", "Month", "kWh", "RM"]].to_excel(
                writer,
                index=False,
                sheet_name="TNB_Data"
            )

        st.download_button(
            "Download Excel",
            output.getvalue(),
            "TNB_Report.xlsx"
        )

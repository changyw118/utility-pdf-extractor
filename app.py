import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="TNB Precise Industrial Extractor",
    layout="wide"
)

# --------------------------------------------------
# UTILITIES
# --------------------------------------------------
def clean_industrial_num(raw):
    if not raw:
        return 0.0
    raw = raw.replace(" ", "")
    raw = "".join(c for c in raw if c.isdigit() or c == ".")
    if raw.count(".") > 1:
        parts = raw.split(".")
        raw = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(raw)
    except:
        return 0.0


def extract_date(text):
    header = re.search(
        r'Tarikh\s*Bil(.*?)No\.\s*Invois',
        text,
        re.IGNORECASE | re.DOTALL
    )
    if not header:
        return None

    dates = re.findall(
        r'(\d{2}[./-]\d{2}[./-]\d{4})',
        header.group(1)
    )
    if len(dates) >= 2:
        raw = dates[1].replace("-", ".").replace("/", ".")
        if raw.startswith("9"):
            raw = "3" + raw[1:]
        try:
            return datetime.strptime(raw, "%d.%m.%Y")
        except:
            return None
    return None


def extract_values(text):
    kwh = 0.0
    rm = 0.0

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        if "kwh" in line.lower():
            kwh = clean_industrial_num(line)

        if "perlu bayar" in line.lower():
            rm = clean_industrial_num(line)

    return kwh, rm


# --------------------------------------------------
# OCR PIPELINE (ROBUST VERSION)
# --------------------------------------------------
def extract_data_with_ocr(pdf_file):
    results = []
    last_valid_date = None

    pdf_file.seek(0)
    file_bytes = pdf_file.read()

    # count pages safely
    pages = convert_from_bytes(file_bytes, dpi=50)
    total_pages = len(pages)
    del pages
    gc.collect()

    progress = st.progress(0, text=f"Scanning {pdf_file.name}")

    for page in range(1, total_pages + 1):
        progress.progress(int(page / total_pages * 100))

        images = convert_from_bytes(
            file_bytes,
            dpi=200,
            first_page=page,
            last_page=page,
            grayscale=True
        )

        image = images[0]

        text_6 = pytesseract.image_to_string(image, config="--psm 6")
        text_11 = pytesseract.image_to_string(image, config="--psm 11")
        text = text_6 if len(text_6) > len(text_11) else text_11

        # DATE (carry-forward logic)
        dt = extract_date(text)
        if dt:
            last_valid_date = dt
        else:
            dt = last_valid_date

        if not dt or not (2010 <= dt.year <= 2030):
            image.close()
            continue

        # VALUES
        kwh, rm = extract_values(text)

        # SANITY FILTER
        if kwh > 50_000_000 or rm > 5_000_000:
            image.close()
            continue

        if kwh > 0 or rm > 0:
            results.append({
                "Year": dt.year,
                "Month": dt.strftime("%b"),
                "Month_Num": dt.month,
                "kWh": kwh,
                "RM": rm
            })

        image.close()
        del image
        gc.collect()

    progress.empty()
    return results


# --------------------------------------------------
# UI
# --------------------------------------------------
st.title("⚡ TNB Industrial Smart Extractor")

uploaded_files = st.file_uploader(
    "Upload TNB PDFs",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    all_data = []

    for f in uploaded_files:
        all_data.extend(extract_data_with_ocr(f))

    if all_data:
        df = (
            pd.DataFrame(all_data)
            .drop_duplicates(subset=["Year", "Month"])
            .sort_values(["Year", "Month_Num"])
        )

        st.subheader("Extracted Summary")
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
            workbook = writer.book
            worksheet = writer.sheets["TNB_Data"]
            fmt = workbook.add_format({"num_format": "#,##0.00"})
            worksheet.set_column("C:D", 20, fmt)

        st.download_button(
            "Download Formatted Excel Report",
            output.getvalue(),
            "TNB_Precise_Report.xlsx"
        )

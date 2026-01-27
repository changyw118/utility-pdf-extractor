import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import gc
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="TNB Precise Industrial Extractor", layout="wide")

# --- AUTO-PATH FINDER ---
def find_poppler():
    """Tries to find the poppler bin folder automatically on C: drive"""
    search_locations = [
        r"C:\poppler\Library\bin",
        r"C:\poppler\poppler-25.12.0\Library\bin",
        r"C:\poppler-25.12.0\Library\bin",
        r"C:\Program Files\poppler\bin"
    ]
    for path in search_locations:
        if os.path.exists(os.path.join(path, "pdfinfo.exe")):
            return path
    return ""

# --- SIDEBAR SETUP ---
st.sidebar.header("🔧 Windows Configuration")
st.sidebar.markdown("The script will try to find Poppler automatically.")

suggested_pop = find_poppler()
poppler_path = st.sidebar.text_input("Poppler Bin Path", value=suggested_pop)
tesseract_exe = st.sidebar.text_input("Tesseract EXE Path", value=r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# --- CORE LOGIC ---
def clean_num(raw_str):
    if not raw_str: return 0.0
    clean = re.sub(r'[^\d.]', '', raw_str.replace(' ', '').replace(',', ''))
    try:
        return float(clean)
    except:
        return 0.0

def process_bill(pdf_file, p_path, t_path):
    data_list = []
    
    # Configure Tesseract
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
    else:
        st.error(f"❌ Tesseract not found at: {t_path}")
        return None

    try:
        # 1. Convert PDF to Images
        pdf_file.seek(0)

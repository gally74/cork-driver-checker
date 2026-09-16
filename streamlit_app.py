"""Browser checker for Cork Driver crew arrangements.

Upload one day's circular PDF (Monday_pages.pdf, etc.).
Optionally upload that day's Word daily sheet to mark Found/Missing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cork_driver_checker import (
    DAYS,
    compare_item_to_sheet,
    format_checklist,
    parse_day_pdf,
    read_word_text,
)


st.set_page_config(page_title="Cork Driver Checker", layout="centered")

st.title("Cork Driver Checker")
st.caption("One day at a time: Monday circular against Monday sheet.")

day = st.selectbox("Which day?", DAYS, index=0)

pdf_file = st.file_uploader(
    "Upload that day's circular pages (e.g. Monday_pages.pdf)",
    type=["pdf"],
)

sheet_file = st.file_uploader(
    "Optional: that day's Word daily sheet",
    type=["docx", "docm"],
)

run = st.button("Build checklist", type="primary", disabled=pdf_file is None)

if run and pdf_file is not None:
    suffix = Path(pdf_file.name).suffix or ".pdf"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = tmp_dir / f"{day}_pages.pdf"
        pdf_path.write_bytes(pdf_file.getvalue())

        sheet_path = None
        if sheet_file is not None:
            sheet_path = tmp_dir / sheet_file.name
            sheet_path.write_bytes(sheet_file.getvalue())

        try:
            items, carry = parse_day_pdf(pdf_path, day)
            if sheet_path:
                sheet_text = read_word_text(sheet_path)
                for item in items:
                    compare_item_to_sheet(item, sheet_text)
            week_dir = Path(pdf_file.name)
            checklist = format_checklist(day, week_dir, items, carry, sheet_path)
        except Exception as exc:
            st.error(f"Could not read that PDF. {exc}")
            st.stop()

    missing = sum(1 for item in items if item.sheet_status == "MISSING")
    found = sum(1 for item in items if item.sheet_status == "FOUND")

    if sheet_path:
        st.success(f"{len(items)} Cork Driver item(s). {found} found, {missing} missing.")
    else:
        st.info(
            f"{len(items)} Cork Driver item(s). "
            "No daily sheet uploaded, so tick these by hand while you build Monday."
        )

    st.download_button(
        f"Download {day}_Cork_Driver_checklist.txt",
        data=checklist.encode("utf-8"),
        file_name=f"{day}_Cork_Driver_checklist.txt",
        mime="text/plain",
    )
    st.text_area("Checklist", checklist, height=420)

st.divider()
st.markdown(
    """
**How to use each week**
1. Pick the day (start with Monday).
2. Upload that day's pages PDF from the weekly circular split.
3. Click **Build checklist** and tick the items onto the daily sheet.
4. After the Word sheet is saved, upload it too to mark Found / Missing.
"""
)

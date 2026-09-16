"""Browser checker for Cork Driver crew arrangements.

Upload one day's circular PDF. Optionally upload that day's Word daily sheet
to compare circular items against Job Analysis.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cork_driver_checker import (
    DAYS,
    compare_item_to_sheet,
    format_checklist,
    format_compare_csv,
    format_compare_report,
    parse_day_pdf,
    read_word_text,
)


st.set_page_config(page_title="Cork Driver Checker", layout="centered")

st.title("Cork Driver Checker")
st.caption(
    "One day at a time. Compare needs both times (e.g. 0540 and 1047) plus the station (Portlaoise)."
)

day = st.selectbox("Which day?", DAYS, index=0)

pdf_file = st.file_uploader(
    "Upload that day's circular pages (e.g. Monday_pages.pdf)",
    type=["pdf"],
)

sheet_file = st.file_uploader(
    "Optional: that day's Word daily sheet (for compare)",
    type=["docx", "docm"],
)

button_label = "Compare circular and daily sheet" if sheet_file else "Build checklist"
run = st.button(button_label, type="primary", disabled=pdf_file is None)

if run and pdf_file is not None:
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
            compare = ""
            compare_csv = ""
            if sheet_path:
                compare = format_compare_report(
                    day, pdf_file.name, sheet_file.name, items, carry
                )
                compare_csv = format_compare_csv(day, items, carry)
        except Exception as exc:
            st.error(f"Could not read those files. {exc}")
            st.stop()

    missing_items = [item for item in items if item.sheet_status == "MISSING"]
    found_items = [item for item in items if item.sheet_status == "FOUND"]

    if sheet_path:
        if missing_items:
            st.error(
                f"{len(missing_items)} missing on the daily sheet, "
                f"{len(found_items)} found, {len(items)} total."
            )
        else:
            st.success(f"All {len(items)} Cork Driver item(s) were found on the daily sheet.")

        st.download_button(
            f"Download {day} compare (.txt)",
            data=compare.encode("utf-8"),
            file_name=f"{day}_Cork_Driver_compare.txt",
            mime="text/plain",
            key="download_compare_txt",
        )
        st.download_button(
            f"Download {day} compare (.csv)",
            data=compare_csv.encode("utf-8"),
            file_name=f"{day}_Cork_Driver_compare.csv",
            mime="text/csv",
            key="download_compare_csv",
        )

        st.subheader("Missing")
        if not missing_items:
            st.write("None.")
        else:
            for item in missing_items:
                st.markdown(
                    f"**Circular:** {item.cork_duty}  \n"
                    f"**On daily sheet:** {item.sheet_match or 'not found'}  \n"
                    f"**Note:** {item.sheet_note}"
                )

        st.subheader("Found")
        if not found_items:
            st.write("None.")
        else:
            for item in found_items:
                st.markdown(
                    f"**Circular:** {item.cork_duty}  \n"
                    f"**On daily sheet:** {item.sheet_match or item.sheet_note}"
                )

        if carry:
            st.subheader("Carry forward")
            for note in carry:
                st.write(f"- {note}")

        st.text_area("Full compare", compare, height=360)
    else:
        st.info(
            f"{len(items)} Cork Driver item(s). "
            "Upload the Word daily sheet as well to compare Found / Missing."
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
2. Upload that day's pages PDF.
3. To compare, also upload that day's Word daily sheet.
4. Download the compare file. **Missing** items still need to go on the sheet.
"""
)

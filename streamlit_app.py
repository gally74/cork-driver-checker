"""Browser checker for Cork Driver crew arrangements.

Modes:
  - Extract for daily sheet: upload PDF → copy/paste text (website default)
  - One day: day PDF + that day's Word sheet (home/compare — unchanged)
  - Whole week: full circular PDF + Mon-Sun weekly Word sheet (unchanged)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cork_driver_checker import (
    DAYS,
    compare_item_to_sheet,
    extract_for_daily_sheet,
    format_checklist,
    format_compare_csv,
    format_compare_report,
    parse_day_pdf,
    read_word_text,
    run_week_compare,
)


st.set_page_config(page_title="Cork / Mallow / Tralee Checker", layout="centered")

st.title("Cork / Mallow / Tralee Checker")
st.caption(
    "Extract Cork / Mallow / Tralee Driver lines → copy into Word. "
    "Compare modes still need both times (e.g. 0540 and 1047) plus the station."
)

mode = st.radio(
    "Mode",
    ["Extract for daily sheet", "One day", "Whole week"],
    horizontal=True,
    help=(
        "Extract = upload PDF and copy text into Word. "
        "One day / Whole week = existing compare tools (unchanged)."
    ),
)

if mode == "Extract for daily sheet":
    st.subheader("Upload → Extract → Copy into Word")
    pdf_file = st.file_uploader(
        "Upload circular PDF (full week e.g. 4255.pdf, or one day's pages)",
        type=["pdf"],
        key="extract_pdf",
    )
    day_choice = st.selectbox(
        "Which day?",
        ["All days (full circular)"] + list(DAYS),
        index=0,
        help="Use All days for a full weekly circular. Pick a day for Monday_pages.pdf etc.",
    )
    run_extract = st.button(
        "Extract for daily sheet",
        type="primary",
        disabled=pdf_file is None,
    )

    if run_extract and pdf_file is not None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            pdf_path = tmp_dir / pdf_file.name
            pdf_path.write_bytes(pdf_file.getvalue())
            day = None if day_choice.startswith("All days") else day_choice
            try:
                items_by_day, carry_by_day, paste_text = extract_for_daily_sheet(
                    pdf_path, day=day
                )
            except Exception as exc:
                st.error(f"Could not extract that PDF. {exc}")
                st.stop()

        total = sum(len(v) for v in items_by_day.values())
        st.success(f"Extracted {total} Cork Driver item(s). Select the text below and copy (Ctrl+A / Ctrl+C).")

        for d in DAYS:
            items = items_by_day.get(d, [])
            if d not in items_by_day:
                continue
            st.write(f"**{d}:** {len(items)} item(s)")

        st.download_button(
            "Download extract (.txt)",
            data=paste_text.encode("utf-8"),
            file_name="Cork_Driver_daily_sheet_extract.txt",
            mime="text/plain",
            key="download_extract_txt",
        )
        st.text_area("Copy this into your Word daily sheet", paste_text, height=480)

elif mode == "One day":
    day = st.selectbox("Which day?", DAYS, index=0)
    pdf_file = st.file_uploader(
        "Upload that day's circular pages (e.g. Monday_pages.pdf)",
        type=["pdf"],
        key="day_pdf",
    )
    sheet_file = st.file_uploader(
        "Optional: that day's Word daily sheet (for compare)",
        type=["docx", "docm"],
        key="day_sheet",
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
                st.success(
                    f"All {len(items)} Cork Driver item(s) were found on the daily sheet."
                )

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

else:
    circular_file = st.file_uploader(
        "Upload the full weekly circular PDF (e.g. 4255.pdf)",
        type=["pdf"],
        key="week_pdf",
    )
    weekly_sheet_file = st.file_uploader(
        "Upload the weekly daily sheet (Mon-Sun Word file, e.g. 21 Sep to 27 Sep.docm)",
        type=["docx", "docm"],
        key="week_sheet",
    )
    run_week = st.button(
        "Compare whole week",
        type="primary",
        disabled=circular_file is None or weekly_sheet_file is None,
    )

    if run_week and circular_file is not None and weekly_sheet_file is not None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            circular_path = tmp_dir / circular_file.name
            sheet_path = tmp_dir / weekly_sheet_file.name
            circular_path.write_bytes(circular_file.getvalue())
            sheet_path.write_bytes(weekly_sheet_file.getvalue())
            try:
                items_by_day, carry_by_day, report, csv_text = run_week_compare(
                    circular_path, sheet_path
                )
            except Exception as exc:
                st.error(f"Could not compare those files. {exc}")
                st.stop()

        total_items = sum(len(v) for v in items_by_day.values())
        total_missing = sum(
            1
            for items in items_by_day.values()
            for item in items
            if item.sheet_status == "MISSING"
        )
        total_found = sum(
            1
            for items in items_by_day.values()
            for item in items
            if item.sheet_status == "FOUND"
        )

        if total_missing:
            st.error(
                f"Week: {total_missing} missing, {total_found} found, {total_items} total."
            )
        else:
            st.success(f"Week: all {total_items} Cork Driver item(s) found.")

        st.download_button(
            "Download week compare (.txt)",
            data=report.encode("utf-8"),
            file_name="Week_Cork_Driver_compare.txt",
            mime="text/plain",
            key="week_txt",
        )
        st.download_button(
            "Download week compare (.csv)",
            data=csv_text.encode("utf-8"),
            file_name="Week_Cork_Driver_compare.csv",
            mime="text/csv",
            key="week_csv",
        )

        st.subheader("Summary by day")
        for day in DAYS:
            items = items_by_day.get(day, [])
            missing = sum(1 for item in items if item.sheet_status == "MISSING")
            found = sum(1 for item in items if item.sheet_status == "FOUND")
            st.write(f"**{day}:** {len(items)} items — {found} found, {missing} missing")

        st.subheader("Missing")
        shown = 0
        for day in DAYS:
            for item in items_by_day.get(day, []):
                if item.sheet_status != "MISSING":
                    continue
                shown += 1
                st.markdown(
                    f"**[{day}] Circular:** {item.cork_duty}  \n"
                    f"**On daily sheet:** {item.sheet_match or 'not found'}  \n"
                    f"**Note:** {item.sheet_note}"
                )
        if shown == 0:
            st.write("None.")

        st.text_area("Full week compare", report, height=420)

st.divider()
st.markdown(
    """
**How to use**
- **Extract for daily sheet:** upload the circular PDF → Cork / Mallow / Tralee Driver lines → copy into Word.
- **One day / Whole week:** existing compare tools (home PC / Codespaces) — unchanged.
- **Weekly Rosters → Scan Circulars** on the home PC is separate and untouched.
"""
)
